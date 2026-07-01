import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager
from enum import Enum as EnumType
from typing import Any

from msgspec import UNSET

from specstar.query_types import (
    AggKeyRef,
    AggSpec,
    DataSearchFilter,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    FieldTransform,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    VectorDistanceCondition,
    VectorDistanceSort,
)
from specstar.resource_manager import _pg_pool
from specstar.resource_manager.basic import (
    Encoding,
    IMetaWithAgg,
    ISlowMetaStore,
    MsgspecSerializer,
)
from specstar.types import ResourceMeta

try:
    import psycopg2 as pg
    import psycopg2.pool
    from psycopg2.extras import DictCursor, execute_batch
except ImportError:  # pragma: no cover
    pg = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
    psycopg2 = None  # type: ignore[assignment]  # noqa: F811  # ty:ignore[invalid-assignment]
    DictCursor = None  # type: ignore[assignment,misc]  # ty:ignore[invalid-assignment]
    execute_batch = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]


class PostgresMetaStore(IMetaWithAgg, ISlowMetaStore):
    """PostgreSQL-backed metadata store.

    All stores resolving to the same DSN share one process-global
    connection pool (#380), so connection count scales with the number of
    distinct DSNs rather than the number of models. ``minconn`` defaults to
    ``0`` (lazy) and ``maxconn`` to ``16`` — a per-process, per-DSN ceiling
    shared across every store on that DSN, tunable for high concurrency.
    """

    def __init__(
        self,
        pg_dsn: str,
        encoding: Encoding = Encoding.json,
        *,
        table_name: str = "resource_meta",
        minconn: int = _pg_pool.DEFAULT_MINCONN,
        maxconn: int = _pg_pool.DEFAULT_MAXCONN,
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )

        # Share one process-global pool per DSN (#380). The pool is owned by
        # the registry for the process lifetime; this store never closes it.
        self._pg_dsn = pg_dsn
        self._conn_pool = _pg_pool.get_pool(pg_dsn, minconn=minconn, maxconn=maxconn)
        self.table_name = table_name
        # field_path → (indexed_dim, distance) for pgvector columns
        self._vec_columns: dict[str, tuple[int, str]] = {}
        # Field paths registered as list-typed. ``contains`` on these uses
        # JSONB ``@>`` instead of the substring-based ``LIKE``. See #362.
        self._list_fields: set[str] = set()
        # field_path → pg element type (e.g. "text") for SetIndex array columns
        self._set_columns: dict[str, str] = {}

        # 初始化 PostgreSQL 表
        self._init_postgres_table()
        self._has_pgvector = self._detect_pgvector()

    def _detect_pgvector(self) -> bool:
        # Use a dedicated raw connection to avoid touching the pool — pool
        # mock-based tests rely on a fixed iteration count.
        try:
            conn = psycopg2.connect(self._pg_dsn)
        except BaseException:
            return False
        try:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_extension WHERE extname = 'vector' LIMIT 1"
                )
                return cur.fetchone() is not None
        except BaseException:
            return False
        finally:
            try:
                conn.close()
            except BaseException:
                pass

    @property
    def supports_native_vector_search(self) -> bool:
        return self._has_pgvector

    def register_list_field(self, field_path: str) -> None:
        """Declare *field_path* as a list-typed indexed field.

        Routes ``DataSearchOperator.contains`` on this field through JSONB
        ``@>`` (true element containment) instead of the default ``LIKE``
        substring match. Idempotent — safe to call from ``add_model`` on
        every registration.

        See #362.
        """
        self._list_fields.add(field_path)

    # ------------------------------------------------------------------
    # Vector / pgvector DDL helpers
    # ------------------------------------------------------------------

    # pgvector HNSW upper bound for indexable dim.
    HNSW_MAX_DIM = 2000

    _DISTANCE_OPS = {
        "cosine": ("vector_cosine_ops", "<=>"),
        "l2": ("vector_l2_ops", "<->"),
        "ip": ("vector_ip_ops", "<#>"),
    }

    def _vec_col_name(self, field_path: str) -> str:
        # JSON paths use ".", which is invalid in column identifiers
        return "vec_" + field_path.replace(".", "_")

    def ensure_vector_column(
        self,
        field_path: str,
        *,
        dim: int,
        distance: str = "cosine",
    ) -> None:
        """Create a pgvector column + HNSW index for *field_path*.

        Idempotent: skips when the column / index already exists.  When
        ``dim`` exceeds :pyattr:`HNSW_MAX_DIM`, only the first
        ``HNSW_MAX_DIM`` dimensions are indexed (Matryoshka prefix
        strategy).
        """
        if not self._has_pgvector:
            raise RuntimeError(
                "PostgresMetaStore: pgvector extension is required for "
                "vector fields. Run `CREATE EXTENSION vector;` as superuser."
            )

        ops_class, _op = self._DISTANCE_OPS.get(distance, self._DISTANCE_OPS["cosine"])
        col = self._vec_col_name(field_path)
        indexed_dim = min(dim, self.HNSW_MAX_DIM)
        idx_name = f"idx_{self.table_name}_{col}_hnsw"

        # ALTER TABLE / CREATE INDEX CONCURRENTLY cannot run inside a
        # transaction.  Pool connections are managed with autocommit=False,
        # so open a dedicated raw connection for DDL and close it after.
        conn = psycopg2.connect(self._pg_dsn)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f'ALTER TABLE "{self.table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{col}" vector({indexed_dim})'
                )
                cur.execute(
                    f'CREATE INDEX IF NOT EXISTS "{idx_name}" '
                    f'ON "{self.table_name}" '
                    f'USING hnsw ("{col}" {ops_class})'
                )
        finally:
            conn.close()

        self._vec_columns[field_path] = (indexed_dim, distance)

    # ------------------------------------------------------------------
    # SetIndex (array set-overlap) DDL helpers
    # ------------------------------------------------------------------

    # Python element type → Postgres array element type.
    _SET_ELEM_TYPES: dict[type, str] = {
        str: "text",
        int: "bigint",
        float: "double precision",
    }

    def _set_col_name(self, field_path: str) -> str:
        return "set_" + field_path.replace(".", "_")

    def ensure_set_column(self, field_path: str, elem_type: type = str) -> None:
        """Create a dedicated array column + GIN for *field_path* so
        ``contains_any`` runs as one indexed ``&&`` overlap instead of a
        per-candidate ``@>`` fan-out on the shared index.

        Idempotent; mirrors :meth:`ensure_vector_column` (pgvector). Other
        backends serve ``contains_any`` from the shared path and need no
        shadow column, so this is Postgres-only native acceleration.
        """
        pg_elem = self._SET_ELEM_TYPES.get(elem_type, "text")
        col = self._set_col_name(field_path)
        idx_name = f"idx_{self.table_name}_{col}_gin"
        # ALTER TABLE / CREATE INDEX can't run inside the pool's txn; use a
        # dedicated autocommit connection for DDL (same as ensure_vector_column).
        conn = psycopg2.connect(self._pg_dsn)
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f'ALTER TABLE "{self.table_name}" '
                    f'ADD COLUMN IF NOT EXISTS "{col}" {pg_elem}[]'
                )
                cur.execute(
                    f'CREATE INDEX IF NOT EXISTS "{idx_name}" '
                    f'ON "{self.table_name}" USING GIN ("{col}")'
                )
        finally:
            conn.close()
        self._set_columns[field_path] = pg_elem

    def _extract_set_value(self, meta: ResourceMeta, field_path: str) -> "list | None":
        """The list value for a SetIndex column, copied from indexed_data."""
        if meta.indexed_data is UNSET or meta.indexed_data is None:
            return None
        v = meta.indexed_data.get(field_path)
        return v if isinstance(v, list) else None

    def backfill_set_column(self, field_path: str) -> int:
        """Repopulate the SetIndex shadow column for *field_path* from
        ``indexed_data`` across all existing rows — for rows written before the
        column was added (it defaults to NULL there). One pushed-down ``UPDATE``;
        returns rows touched. No-op when the field has no shadow column.

        Analogous to :func:`backfill_vectors` for Vector fields, but the value
        is a pure derivation of ``indexed_data`` (no re-encoding needed), so it
        runs entirely in SQL.
        """
        if field_path not in self._set_columns:
            return 0
        pg_elem = self._set_columns[field_path]
        col = self._set_col_name(field_path)
        extract = "jsonb_array_elements_text(indexed_data->%s)"
        arr = (
            f"ARRAY(SELECT {extract})"
            if pg_elem == "text"
            else f"ARRAY(SELECT ({extract})::{pg_elem})"
        )
        sql = (
            f'UPDATE "{self.table_name}" SET "{col}" = {arr} '
            f"WHERE jsonb_typeof(indexed_data->%s) = 'array'"
        )
        with self.transaction() as cur:
            cur.execute(sql, [field_path, field_path])
            return cur.rowcount

    def _build_vector_condition(
        self, condition: "VectorDistanceCondition"
    ) -> tuple[str, list]:
        if condition.field_path not in self._vec_columns:
            return "", []
        if not isinstance(condition.query_vector, list):
            return "", []  # str query_vector must be resolved upstream
        indexed_dim, default_distance = self._vec_columns[condition.field_path]
        metric = condition.distance or default_distance or "cosine"
        _ops, op_symbol = self._DISTANCE_OPS[metric]
        col = self._vec_col_name(condition.field_path)
        clipped = condition.query_vector[:indexed_dim]
        vec_literal = self._format_vec_literal(clipped)
        op_map = {
            DataSearchOperator.less_than: "<",
            DataSearchOperator.less_than_or_equal: "<=",
            DataSearchOperator.greater_than: ">",
            DataSearchOperator.greater_than_or_equal: ">=",
        }
        sql_op = op_map.get(condition.operator)
        if sql_op is None:
            return "", []
        return (
            f'"{col}" {op_symbol} %s::vector {sql_op} %s',
            [vec_literal, float(condition.threshold)],
        )

    def _build_vector_order(self, sort: "VectorDistanceSort") -> tuple[str, list]:
        if sort.field_path not in self._vec_columns:
            return "", []
        if not isinstance(sort.query_vector, list):
            return "", []
        indexed_dim, default_distance = self._vec_columns[sort.field_path]
        metric = sort.distance or default_distance or "cosine"
        _ops, op_symbol = self._DISTANCE_OPS[metric]
        col = self._vec_col_name(sort.field_path)
        clipped = sort.query_vector[:indexed_dim]
        vec_literal = self._format_vec_literal(clipped)
        direction = (
            "ASC" if sort.direction == ResourceMetaSortDirection.ascending else "DESC"
        )
        return f'"{col}" {op_symbol} %s::vector {direction}', [vec_literal]

    @staticmethod
    def _format_vec_literal(vec: list[float]) -> str:
        """pgvector accepts vector input as the string '[v1,v2,...]'."""
        return "[" + ",".join(str(float(v)) for v in vec) + "]"

    def _extract_vec_value(
        self, meta: ResourceMeta, field_path: str, indexed_dim: int
    ) -> str | None:
        """Pull the vector value out of meta.indexed_data and clip to indexed_dim."""
        if meta.indexed_data is UNSET or meta.indexed_data is None:
            return None
        # Support dotted paths like "summary.vector"
        cur: object = meta.indexed_data
        for part in field_path.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        if not isinstance(cur, list):
            return None
        clipped = cur[:indexed_dim]
        if len(clipped) != indexed_dim:
            return None  # under-dim vector — leave NULL
        return self._format_vec_literal(clipped)

    # The connection pool is shared across all stores on this DSN and owned
    # by the process-global registry (#380); a store must not close it on
    # garbage collection. Use ``_pg_pool.close_all_pools()`` for explicit
    # shutdown / test teardown.

    def get_conn(self) -> Any:
        retry = 5
        last_error: Exception | None = None
        for attempt in range(retry):
            try:
                conn = self._conn_pool.getconn()
            except psycopg2.pool.PoolError:
                # Pool 耗盡，等待後重試（其他 thread 可能會歸還連線）
                last_error = psycopg2.pool.PoolError("connection pool exhausted")
                time.sleep(min(0.5 * (attempt + 1), 3))
                continue

            conn.autocommit = False
            if self.test_query(conn):
                return conn

            # test_query 失敗：歸還壞連線並標記關閉，避免洩漏
            try:
                self._conn_pool.putconn(conn, close=True)
            except Exception:
                pass
            last_error = ConnectionError("Failed to get a valid PostgreSQL connection.")
            time.sleep(1)

        if isinstance(last_error, psycopg2.pool.PoolError):
            raise last_error
        raise ConnectionError("Failed to get a valid PostgreSQL connection.")

    def put_conn(self, conn):
        self._conn_pool.putconn(conn)

    def test_query(self, conn) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone()[0] == 1
        except Exception:
            return False

    @contextmanager
    def transaction(self):
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.put_conn(conn)

    @contextmanager
    def stream_cursor(self):
        conn = self.get_conn()
        try:
            # 建立 server-side cursor (named cursor)
            with conn.cursor(
                name="PostgresMetaStore",
                cursor_factory=DictCursor,
            ) as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.put_conn(conn)

    def _init_postgres_table(self):
        """初始化 PostgreSQL 表結構"""
        with self.transaction() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS "{self.table_name}" (
                    resource_id TEXT PRIMARY KEY,
                    data BYTEA NOT NULL,
                    created_time TIMESTAMP NOT NULL,
                    updated_time TIMESTAMP NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    is_deleted BOOLEAN NOT NULL,
                    schema_version TEXT,
                    indexed_data JSONB,  -- JSON 格式的索引數據
                    rev_status TEXT,
                    rev_created_by TEXT,
                    rev_updated_by TEXT,
                    rev_created_time TIMESTAMP,
                    rev_updated_time TIMESTAMP
                )
            """)

            # 檢查是否需要添加 indexed_data 欄位（用於向後兼容）
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{self.table_name}' AND column_name = 'indexed_data'
            """)
            if not cur.fetchone():
                cur.execute(
                    f'ALTER TABLE "{self.table_name}" ADD COLUMN indexed_data JSONB'
                )

            # 檢查是否需要添加 schema_version 欄位（用於向後兼容）
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{self.table_name}' AND column_name = 'schema_version'
            """)
            if not cur.fetchone():
                cur.execute(
                    f'ALTER TABLE "{self.table_name}" ADD COLUMN schema_version TEXT'
                )

            # 為 rev_* 欄位逐一檢查並補欄（向後兼容舊表）
            for col_name, col_type in (
                ("rev_status", "TEXT"),
                ("rev_created_by", "TEXT"),
                ("rev_updated_by", "TEXT"),
                ("rev_created_time", "TIMESTAMP"),
                ("rev_updated_time", "TIMESTAMP"),
            ):
                cur.execute(
                    f"""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = '{self.table_name}' AND column_name = '{col_name}'
                    """
                )
                if not cur.fetchone():
                    cur.execute(
                        f'ALTER TABLE "{self.table_name}" ADD COLUMN {col_name} {col_type}'
                    )

            # 創建索引
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_created_time ON "{self.table_name}"(created_time)',
            )
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_updated_time ON "{self.table_name}"(updated_time)',
            )
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_created_by ON "{self.table_name}"(created_by)',
            )
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_updated_by ON "{self.table_name}"(updated_by)',
            )
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_is_deleted ON "{self.table_name}"(is_deleted)',
            )
            for col_name in (
                "rev_status",
                "rev_created_by",
                "rev_updated_by",
                "rev_created_time",
                "rev_updated_time",
            ):
                cur.execute(
                    f'CREATE INDEX IF NOT EXISTS idx_{col_name} ON "{self.table_name}"({col_name})'
                )
            # 為 JSONB 創建 GIN 索引以提高查詢效能
            cur.execute(
                f'CREATE INDEX IF NOT EXISTS idx_indexed_data_gin ON "{self.table_name}" USING GIN (indexed_data)',
            )

            # 遷移已存在的記錄，填充 indexed_data
            self._migrate_existing_data(cur)

    def _migrate_existing_data(self, cur):
        """為已存在但沒有 indexed_data 的記錄填充索引數據"""
        import json

        cur.execute(f"""
            SELECT resource_id, data FROM "{self.table_name}" 
            WHERE indexed_data IS NULL
        """)

        for resource_id, data_blob in cur.fetchall():
            try:
                data = self._serializer.decode(data_blob)
                indexed_data_json = (
                    json.dumps(data.indexed_data, ensure_ascii=False)
                    if data.indexed_data is not UNSET
                    else None
                )
                cur.execute(
                    f"""
                    UPDATE "{self.table_name}" SET indexed_data = %s WHERE resource_id = %s
                """,
                    (indexed_data_json, resource_id),
                )
            except Exception:
                # 如果解析失敗，設置為空 JSON 對象
                cur.execute(
                    f"""
                    UPDATE "{self.table_name}" SET indexed_data = %s WHERE resource_id = %s
                """,
                    ("{}", resource_id),
                )

    def _meta_row_values(self, meta: ResourceMeta) -> tuple:
        """Pack a ResourceMeta into the column-order tuple used by INSERT/UPSERT."""
        import json

        base = (
            meta.resource_id,
            self._serializer.encode(meta),
            meta.created_time,
            meta.updated_time,
            meta.created_by,
            meta.updated_by,
            meta.is_deleted,
            meta.schema_version,
            (
                json.dumps(meta.indexed_data, ensure_ascii=False)
                if meta.indexed_data is not UNSET
                else None
            ),
            meta.rev_status if meta.rev_status is not UNSET else None,
            meta.rev_created_by if meta.rev_created_by is not UNSET else None,
            meta.rev_updated_by if meta.rev_updated_by is not UNSET else None,
            meta.rev_created_time if meta.rev_created_time is not UNSET else None,
            meta.rev_updated_time if meta.rev_updated_time is not UNSET else None,
        )
        # Append registered vec column values in deterministic order
        for field_path, (indexed_dim, _) in self._vec_columns.items():
            base = base + (self._extract_vec_value(meta, field_path, indexed_dim),)
        # Then SetIndex array column values, same deterministic order.
        for field_path in self._set_columns:
            base = base + (self._extract_set_value(meta, field_path),)
        return base

    def _upsert_sql(self) -> str:
        vec_cols = [self._vec_col_name(fp) for fp in self._vec_columns]
        set_cols = [self._set_col_name(fp) for fp in self._set_columns]
        base_cols = [
            "resource_id",
            "data",
            "created_time",
            "updated_time",
            "created_by",
            "updated_by",
            "is_deleted",
            "schema_version",
            "indexed_data",
            "rev_status",
            "rev_created_by",
            "rev_updated_by",
            "rev_created_time",
            "rev_updated_time",
        ]
        all_cols = base_cols + vec_cols + set_cols
        col_list = ", ".join(f'"{c}"' for c in all_cols)
        # vec values are passed as strings cast to vector; set values as lists
        # cast to the column's array type (psycopg2 adapts a list → array).
        placeholders = ", ".join(
            ["%s"] * len(base_cols)
            + ["%s::vector"] * len(vec_cols)
            + [f"%s::{self._set_columns[fp]}[]" for fp in self._set_columns]
        )
        update_clause = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in all_cols if c != "resource_id"
        )
        return (
            f'INSERT INTO "{self.table_name}" ({col_list}) '
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (resource_id) DO UPDATE SET {update_clause}"
        )

    def save_many(self, metas: Iterable[ResourceMeta]) -> None:
        """批量保存元数据到 PostgreSQL（ISlowMetaStore 接口方法）"""
        metas_list = list(metas)
        if not metas_list:
            return

        with self.transaction() as cur:
            execute_batch(
                cur,
                self._upsert_sql(),
                [self._meta_row_values(m) for m in metas_list],
            )

    def values(self):
        """Streaming bulk read — single ``SELECT data`` instead of N+1 queries."""
        with self.stream_cursor() as cur:
            cur.execute(f'SELECT data FROM "{self.table_name}"')
            for row in cur:
                yield self._serializer.decode(row["data"])

    def __getitem__(self, pk: str) -> ResourceMeta:
        # 直接從 PostgreSQL 查詢
        with self.stream_cursor() as cur:
            cur.execute(
                f'SELECT data FROM "{self.table_name}" WHERE resource_id = %s', (pk,)
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(pk)
            return self._serializer.decode(row["data"])

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:  # ty:ignore[invalid-method-override]
        # 直接寫入 PostgreSQL — honour caller-supplied ``pk`` even if it
        # differs from ``meta.resource_id`` for compat with dict-style usage.
        row = (pk, *self._meta_row_values(meta)[1:])
        with self.transaction() as cur:
            cur.execute(self._upsert_sql(), row)

    def __delitem__(self, pk: str) -> None:
        # 從 PostgreSQL 刪除
        with self.transaction() as cur:
            cur.execute(
                f'DELETE FROM "{self.table_name}" WHERE resource_id = %s', (pk,)
            )
            if cur.rowcount == 0:
                raise KeyError(pk)

    def __iter__(self) -> Generator[str]:
        # 從 PostgreSQL 查询所有 resource_id
        with self.stream_cursor() as cur:
            cur.execute(f'SELECT resource_id FROM "{self.table_name}"')
            for row in cur:
                yield row["resource_id"]

    def __len__(self) -> int:
        # 從 PostgreSQL 计算总数
        with self.stream_cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{self.table_name}"')
            return cur.fetchone()[0]

    def _build_where(self, query: ResourceMetaSearchQuery) -> tuple[str, list]:
        """Translate a search query into a SQL ``WHERE`` clause + params.

        Shared by :meth:`iter_search` and :meth:`aggregate_by` so a pushed-down
        aggregate filters exactly like a search — meta columns + ``indexed_data``
        JSONB conditions + vector conditions, built ONE way. Returns the
        ``"WHERE ..."`` string (``""`` when unfiltered) and its params;
        ordering / paging stay with the caller.
        """
        conditions = []
        params = []

        if query.is_deleted is not UNSET:
            conditions.append("is_deleted = %s")
            params.append(query.is_deleted)

        if query.created_time_start is not UNSET:
            conditions.append("created_time >= %s")
            params.append(query.created_time_start)

        if query.created_time_end is not UNSET:
            conditions.append("created_time <= %s")
            params.append(query.created_time_end)

        if query.updated_time_start is not UNSET:
            conditions.append("updated_time >= %s")
            params.append(query.updated_time_start)

        if query.updated_time_end is not UNSET:
            conditions.append("updated_time <= %s")
            params.append(query.updated_time_end)

        if query.created_bys is not UNSET:
            placeholders = ",".join(["%s"] * len(query.created_bys))
            conditions.append(f"created_by IN ({placeholders})")
            params.extend(query.created_bys)

        if query.updated_bys is not UNSET:
            placeholders = ",".join(["%s"] * len(query.updated_bys))
            conditions.append(f"updated_by IN ({placeholders})")
            params.extend(query.updated_bys)

        if query.rev_statuses is not UNSET:
            placeholders = ",".join(["%s"] * len(query.rev_statuses))
            conditions.append(f"rev_status IN ({placeholders})")
            params.extend(query.rev_statuses)

        if query.rev_created_bys is not UNSET:
            placeholders = ",".join(["%s"] * len(query.rev_created_bys))
            conditions.append(f"rev_created_by IN ({placeholders})")
            params.extend(query.rev_created_bys)

        if query.rev_updated_bys is not UNSET:
            placeholders = ",".join(["%s"] * len(query.rev_updated_bys))
            conditions.append(f"rev_updated_by IN ({placeholders})")
            params.extend(query.rev_updated_bys)

        if query.rev_created_time_start is not UNSET:
            conditions.append("rev_created_time >= %s")
            params.append(query.rev_created_time_start)
        if query.rev_created_time_end is not UNSET:
            conditions.append("rev_created_time <= %s")
            params.append(query.rev_created_time_end)
        if query.rev_updated_time_start is not UNSET:
            conditions.append("rev_updated_time >= %s")
            params.append(query.rev_updated_time_start)
        if query.rev_updated_time_end is not UNSET:
            conditions.append("rev_updated_time <= %s")
            params.append(query.rev_updated_time_end)

        # 處理 data_conditions - 在 PostgreSQL 層面過濾
        if query.data_conditions is not UNSET:
            for condition in query.data_conditions:
                json_condition, json_params = self._build_condition(condition)
                if json_condition:
                    conditions.append(json_condition)
                    params.extend(json_params)

        # 處理 conditions - 在 PostgreSQL 層面過濾
        if query.conditions is not UNSET:
            for condition in query.conditions:
                if isinstance(condition, VectorDistanceCondition):
                    sql_cond, vec_params = self._build_vector_condition(condition)
                    if sql_cond:
                        conditions.append(sql_cond)
                        params.extend(vec_params)
                    continue
                json_condition, json_params = self._build_condition(condition)
                if json_condition:
                    conditions.append(json_condition)
                    params.extend(json_params)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        return where_clause, params

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        where_clause, params = self._build_where(query)

        # 构建排序子句
        order_clause = ""
        order_params: list = []
        if query.sorts is not UNSET and query.sorts:
            order_parts = []
            for sort in query.sorts:
                if isinstance(sort, VectorDistanceSort):
                    sql_part, sort_params = self._build_vector_order(sort)
                    if sql_part:
                        order_parts.append(sql_part)
                        order_params.extend(sort_params)
                    continue
                if isinstance(sort, ResourceMetaSearchSort):
                    direction = (
                        "ASC"
                        if sort.direction == ResourceMetaSortDirection.ascending
                        else "DESC"
                    )
                    order_parts.append(f"{sort.key} {direction}")
                else:
                    # ResourceDataSearchSort - 處理 indexed_data 欄位排序
                    direction = (
                        "ASC"
                        if sort.direction == ResourceMetaSortDirection.ascending
                        else "DESC"
                    )
                    jsonb_extract = f"indexed_data->'{sort.field_path}'"
                    order_parts.append(f"{jsonb_extract} {direction}")
            order_clause = "ORDER BY " + ", ".join(order_parts)
        params.extend(order_params)

        sql = f'SELECT data FROM "{self.table_name}" {where_clause} {order_clause} LIMIT %s OFFSET %s'
        params.append(query.limit)
        params.append(query.offset)

        with self.stream_cursor() as cur:
            cur.execute(sql, params)
            for row in cur:
                yield self._serializer.decode(row["data"])

    def aggregate_by(
        self,
        query: ResourceMetaSearchQuery,
        by: AggKeyRef,
        aggregates: list[AggSpec],
    ) -> list[tuple[object, dict[str, object]]]:
        """Push a ``Count`` group-by down to PostgreSQL — ``GROUP BY`` over the
        filtered set, never materialising one row per match.

        The group key is a real column for ``source="meta"`` or
        ``indexed_data->>'field'`` (JSONB text) for ``source="data"`` (a missing
        field yields SQL ``NULL`` → ``None``, matching the Python path). The
        ``WHERE`` is built by the SAME :meth:`_build_where` as
        :meth:`iter_search`, and NO ``LIMIT``/``OFFSET`` is applied — an
        aggregate spans the whole filtered set.
        """
        # Push-down ops: Count + numeric Sum/Min/Max (Avg is decomposed by the
        # ResourceManager into Sum+Count and never reaches a store). The RM's
        # dispatch predicate only sends eligible specs, so the assert is a
        # defensive guard, not control flow.
        assert all(a.op in ("count", "sum", "min", "max") for a in aggregates), (
            "PostgresMetaStore.aggregate_by supports count/sum/min/max"
        )
        if by.source == "meta":
            key_expr = by.name  # a real column
        else:
            key_expr = f"indexed_data->>'{by.name}'"
        where_clause, params = self._build_where(query)
        select_aggs = ", ".join(
            f"{self._agg_expr(a)} AS a{i}" for i, a in enumerate(aggregates)
        )
        sql = (
            f"SELECT {key_expr} AS k, {select_aggs} "
            f'FROM "{self.table_name}" {where_clause} GROUP BY {key_expr}'
        )
        with self.stream_cursor() as cur:
            cur.execute(sql, params)
            return [
                (row[0], {a.result_name: row[i + 1] for i, a in enumerate(aggregates)})
                for row in cur
            ]

    def _agg_expr(self, a: AggSpec) -> str:
        """SQL for one aggregate's value (not the GROUP BY key). A field-less
        ``count`` is ``COUNT(*)``; a ``count`` WITH a field counts that field's
        non-null values (the denominator for a decomposed ``Avg``) — the raw
        JSONB text, no numeric cast. A numeric value reducer reads a
        ``resource_meta`` column (``source="meta"``) or casts the JSONB text
        ``(indexed_data->>'f')::numeric`` (``source="data"``) so ``SUM``/``MIN``/
        ``MAX`` reduce as numbers (the ResourceManager coerces the result back to
        the field's declared ``int``/``float``)."""
        if a.op == "count" and a.field is None:
            return "COUNT(*)"
        ref = a.field
        assert ref is not None, "value reducer requires a field"
        if a.op == "count":
            base = (
                f'"{ref.name}"'
                if ref.source == "meta"
                else f"(indexed_data->>'{ref.name}')"
            )
            return f"COUNT({base})"
        if a.value_type == "datetime":
            # Reduce a TIMESTAMP meta column and return an absolute Unix epoch:
            # interpret the naive column AS UTC (writes go through a UTC session —
            # see _pg_pool) so the ResourceManager rebuilds the same tz-aware UTC
            # datetime the Python path holds.
            return (
                f"EXTRACT(EPOCH FROM {a.op.upper()}(\"{ref.name}\") AT TIME ZONE 'UTC')"
            )
        if ref.source == "meta":
            base = f'"{ref.name}"'
        else:
            base = f"(indexed_data->>'{ref.name}')::numeric"
        return f"{a.op.upper()}({base})"

    def _build_condition(self, condition: DataSearchFilter) -> tuple[str, list]:
        """構建 PostgreSQL 查詢條件 (支援 Meta 欄位與 JSONB 欄位)"""
        if isinstance(condition, DataSearchGroup):
            sub_conditions = []
            sub_params = []
            for sub_cond in condition.conditions:
                c_str, c_params = self._build_condition(sub_cond)
                if c_str:
                    sub_conditions.append(c_str)
                    sub_params.extend(c_params)

            if not sub_conditions:
                return "", []

            if condition.operator == DataSearchLogicOperator.and_op:
                return f"({' AND '.join(sub_conditions)})", sub_params
            if condition.operator == DataSearchLogicOperator.or_op:
                return f"({' OR '.join(sub_conditions)})", sub_params
            if condition.operator == DataSearchLogicOperator.not_op:
                # NOT (AND(conditions))
                return f"NOT ({' AND '.join(sub_conditions)})", sub_params
            return "", []

        field_path = condition.field_path
        operator = condition.operator
        value = condition.value

        # Normalize Enum to value (indexed data stores Enum as value string)
        if isinstance(value, EnumType):
            value = value.value
        elif isinstance(value, (list, tuple, set)):
            # Handle Enum in lists (for in_list/not_in_list operators)
            value = [v.value if isinstance(v, EnumType) else v for v in value]

        # 判斷是否為 Meta 欄位
        meta_fields = {
            "resource_id",
            "created_time",
            "updated_time",
            "created_by",
            "updated_by",
            "is_deleted",
            "schema_version",
            "rev_status",
            "rev_created_by",
            "rev_updated_by",
            "rev_created_time",
            "rev_updated_time",
        }

        if field_path in meta_fields:
            column_name = field_path

            # Special handling for boolean fields (is_deleted)
            is_boolean_field = field_path == "is_deleted"

            if operator == DataSearchOperator.equals:
                # Handle list/dict comparison for meta fields
                if isinstance(value, (list, dict)):
                    # Cannot compare meta fields to list/dict, skip this condition
                    return "", []
                # Handle incompatible type comparison for boolean fields
                if (
                    is_boolean_field
                    and isinstance(value, (int, float, str))
                    and value not in (True, False)
                ):
                    # PostgreSQL boolean cannot be compared with non-boolean types, skip this condition
                    return "", []
                return f"{column_name} = %s", [value]
            if operator == DataSearchOperator.not_equals:
                # Handle list/dict comparison for meta fields
                if isinstance(value, (list, dict)):
                    # Meta field is never equal to list/dict, so skip this condition (no-op)
                    # Return empty condition to be filtered out by parent AND/OR group
                    return "", []
                # Handle incompatible type comparison for boolean fields
                # PostgreSQL boolean cannot be compared with non-boolean types (int, float, str except boolean values)
                # IMPORTANT: Check bool FIRST because bool is subclass of int in Python!
                if is_boolean_field and not isinstance(value, bool):
                    if isinstance(value, (int, float, str)):
                        # Boolean is never equal to non-boolean values, skip this condition
                        return "", []
                return f"{column_name} != %s", [value]
            if operator == DataSearchOperator.greater_than:
                return f"{column_name} > %s", [value]
            if operator == DataSearchOperator.greater_than_or_equal:
                return f"{column_name} >= %s", [value]
            if operator == DataSearchOperator.less_than:
                return f"{column_name} < %s", [value]
            if operator == DataSearchOperator.less_than_or_equal:
                return f"{column_name} <= %s", [value]
            if operator == DataSearchOperator.contains:
                return f"{column_name} LIKE %s", [f"%{value}%"]
            if operator == DataSearchOperator.starts_with:
                return f"{column_name} LIKE %s", [f"{value}%"]
            if operator == DataSearchOperator.ends_with:
                return f"{column_name} LIKE %s", [f"%{value}"]
            if operator == DataSearchOperator.regex:
                return f"{column_name} ~ %s", [value]
            if operator == DataSearchOperator.in_list:
                if isinstance(value, (list, tuple, set)):
                    placeholders = ",".join(["%s"] * len(value))
                    return f"{column_name} IN ({placeholders})", list(value)
            elif operator == DataSearchOperator.not_in_list:
                if isinstance(value, (list, tuple, set)):
                    placeholders = ",".join(["%s"] * len(value))
                    return f"{column_name} NOT IN ({placeholders})", list(value)
            if operator == DataSearchOperator.is_null:
                if value:
                    return f"{column_name} IS NULL", []
                else:
                    return f"{column_name} IS NOT NULL", []
            if operator == DataSearchOperator.exists:
                if value:
                    return "TRUE", []
                else:
                    return "FALSE", []
            if operator == DataSearchOperator.isna:
                if value:
                    return f"{column_name} IS NULL", []
                else:
                    return f"{column_name} IS NOT NULL", []

            return "", []

        # PostgreSQL JSONB 提取語法: indexed_data->>'field_path'
        # 對於數字比較，使用 (indexed_data->>'field_path')::numeric
        jsonb_text_extract = f"indexed_data->>'{field_path}'"
        jsonb_numeric_extract = f"(indexed_data->>'{field_path}')::numeric"

        # Apply field transformation if specified
        if condition.transform is not None:
            if condition.transform == FieldTransform.length:
                # Get length of JSONB value
                # For arrays: jsonb_array_length()
                # For strings: length(text_value)
                # Use jsonb_typeof to determine type
                jsonb_type = f"jsonb_typeof(indexed_data->'{field_path}')"
                jsonb_text_extract = f"""CASE 
                    WHEN {jsonb_type} = 'array' THEN jsonb_array_length(indexed_data->'{field_path}')
                    WHEN {jsonb_type} = 'string' THEN length(indexed_data->>'{field_path}')
                    ELSE NULL
                END"""
                jsonb_numeric_extract = jsonb_text_extract  # Use same for both

        if operator == DataSearchOperator.equals:
            if isinstance(value, (list, dict)):
                # For list/dict, use JSONB comparison
                import json

                return f"indexed_data->'{field_path}' = %s::jsonb", [json.dumps(value)]
            if isinstance(value, bool):
                return f"{jsonb_text_extract} = %s", ["true" if value else "false"]
            return f"{jsonb_text_extract} = %s", [str(value)]
        if operator == DataSearchOperator.not_equals:
            if isinstance(value, (list, dict)):
                # For list/dict, use JSONB comparison with NULL safe
                import json

                return (
                    f"({jsonb_text_extract} IS NULL OR indexed_data->'{field_path}' != %s::jsonb)",
                    [json.dumps(value)],
                )
            if isinstance(value, bool):
                return f"{jsonb_text_extract} != %s", ["true" if value else "false"]
            return f"{jsonb_text_extract} != %s", [str(value)]
        if operator == DataSearchOperator.greater_than:
            return f"{jsonb_numeric_extract} > %s", [value]
        if operator == DataSearchOperator.greater_than_or_equal:
            return f"{jsonb_numeric_extract} >= %s", [value]
        if operator == DataSearchOperator.less_than:
            return f"{jsonb_numeric_extract} < %s", [value]
        if operator == DataSearchOperator.less_than_or_equal:
            return f"{jsonb_numeric_extract} <= %s", [value]
        if operator == DataSearchOperator.contains:
            # List-typed fields use JSONB ``@>`` so ``contains`` is true
            # element containment, not a substring on the serialised JSON
            # (which produced false-positives like ``"c1"`` matching
            # ``["c10"]``). The default keeps ``LIKE`` for string fields.
            # See #362.
            if field_path in self._list_fields:
                import json

                return (
                    f"indexed_data->'{field_path}' @> %s::jsonb",
                    [json.dumps(value)],
                )
            return f"{jsonb_text_extract} LIKE %s", [f"%{value}%"]
        if operator == DataSearchOperator.starts_with:
            return f"{jsonb_text_extract} LIKE %s", [f"{value}%"]
        if operator == DataSearchOperator.ends_with:
            return f"{jsonb_text_extract} LIKE %s", [f"%{value}"]
        if operator == DataSearchOperator.regex:
            return f"{jsonb_text_extract} ~ %s", [value]
        if operator == DataSearchOperator.in_list:
            if isinstance(value, (list, tuple, set)):
                placeholders = ",".join(["%s"] * len(value))
                return f"{jsonb_text_extract} IN ({placeholders})", [
                    str(v) for v in value
                ]
        elif operator == DataSearchOperator.not_in_list:
            if isinstance(value, (list, tuple, set)):
                placeholders = ",".join(["%s"] * len(value))
                return f"{jsonb_text_extract} NOT IN ({placeholders})", [
                    str(v) for v in value
                ]
        if operator == DataSearchOperator.contains_any:
            vals = list(value) if isinstance(value, (list, tuple, set)) else [value]
            if not vals:
                return "FALSE", []  # empty candidate set matches nothing
            if field_path in self._set_columns:
                # Fast path: ONE indexed array-overlap on the dedicated SetIndex
                # column (its own GIN), instead of the per-candidate @> fan-out.
                # psycopg2 adapts the Python list to an array literal.
                col = self._set_col_name(field_path)
                pg_elem = self._set_columns[field_path]
                return f'"{col}" && %s::{pg_elem}[]', [list(vals)]
            # Fallback (field not SetIndex-declared): OR one ``@>`` containment
            # probe per candidate, served by the SINGLE GIN on the whole
            # ``indexed_data`` (jsonb_ops supports ``@>``). We deliberately do NOT
            # use ``indexed_data->'field' ?| ...`` — that extraction can't use the
            # index — nor a per-field expression index here, which would force
            # CREATE/DROP DDL when indexed fields change and break specstar's "the
            # user never manages the DB / schema can vary freely" guarantee.
            # ``@>`` also scopes to THIS field (a candidate living in another
            # field won't false-match), and the planner BitmapOr's the probes.
            import json

            terms = " OR ".join(["indexed_data @> %s::jsonb"] * len(vals))
            params = [json.dumps({field_path: [v]}, ensure_ascii=False) for v in vals]
            return f"({terms})", params
        if operator == DataSearchOperator.is_null:
            if value:
                # Strict is_null: Must exist AND be null
                return f"(indexed_data ? %s) AND ({jsonb_text_extract} IS NULL)", [
                    field_path
                ]
            else:
                # Strict is_null=False: Must exist AND be NOT null
                # (If it doesn't exist, it's False. If it exists and is null, it's False.)
                # Wait, if is_null=False, we want "Not (Exists and Null)".
                # But user said "if field_path does not exist... return false".
                # So if missing, is_null=False should return False?
                # "is_null(False)" means "is NOT null".
                # If missing, is it "not null"? Yes.
                # But user said "all value related comparisons should return false".
                # If is_null is a value comparison, then is_null(False) on missing should be False.
                # This means "It must exist AND NOT be null".
                return f"(indexed_data ? %s) AND ({jsonb_text_extract} IS NOT NULL)", [
                    field_path
                ]
        if operator == DataSearchOperator.exists:
            if value:
                return "indexed_data ? %s", [field_path]
            else:
                return "NOT (indexed_data ? %s)", [field_path]
        if operator == DataSearchOperator.isna:
            if value:
                return f"{jsonb_text_extract} IS NULL", []
            else:
                return f"{jsonb_text_extract} IS NOT NULL", []

        # 如果不支持的操作，返回空條件
        return "", []
