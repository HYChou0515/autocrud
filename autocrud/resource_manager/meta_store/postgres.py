from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
import time

import psycopg2 as pg
import psycopg2.pool
from msgspec import UNSET
from psycopg2.extras import DictCursor, execute_batch

from autocrud.resource_manager.basic import (
    Encoding,
    ISlowMetaStore,
    MsgspecSerializer,
)
from autocrud.types import (
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
)


class PostgresMetaStore(ISlowMetaStore):
    def __init__(
        self,
        pg_dsn: str,
        encoding: Encoding = Encoding.json,
        *,
        table_name: str = "resource_meta",
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )

        # 建立連線池
        self._conn_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=pg_dsn,
        )
        self.table_name = table_name

        # 初始化 PostgreSQL 表
        self._init_postgres_table()

    def __del__(self):
        # 物件被回收時自動清理
        with suppress(Exception):
            self._cleanup()

    def _cleanup(self):
        # 額外嘗試把所有連線都回收一遍，防止池中連線還被占用
        conns = []
        while True:
            try:
                conn = self._conn_pool.getconn(timeout=1)
                conns.append(conn)
            except Exception:
                break
        for conn in conns:
            with suppress(Exception):
                conn.close()
        with suppress(Exception):
            self._conn_pool.closeall()

    def get_conn(self) -> pg.extensions.connection:
        retry = 5
        for _ in range(retry):
            conn = self._conn_pool.getconn()
            conn.autocommit = False
            if self.test_query(conn):
                return conn
            time.sleep(1)
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
                    indexed_data JSONB  -- JSON 格式的索引數據
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

    def save_many(self, metas: Iterable[ResourceMeta]) -> None:
        """批量保存元数据到 PostgreSQL（ISlowMetaStore 接口方法）"""
        import json

        metas_list = list(metas)
        if not metas_list:
            return

        sql = f"""
        INSERT INTO "{self.table_name}" (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted, schema_version, indexed_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (resource_id) DO UPDATE SET
            data = EXCLUDED.data,
            created_time = EXCLUDED.created_time,
            updated_time = EXCLUDED.updated_time,
            created_by = EXCLUDED.created_by,
            updated_by = EXCLUDED.updated_by,
            is_deleted = EXCLUDED.is_deleted,
            schema_version = EXCLUDED.schema_version,
            indexed_data = EXCLUDED.indexed_data
        """

        with self.transaction() as cur:
            execute_batch(
                cur,
                sql,
                [
                    (
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
                    )
                    for meta in metas_list
                ],
            )

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

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        # 直接寫入 PostgreSQL
        import json

        sql = f"""
        INSERT INTO "{self.table_name}" (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted, schema_version, indexed_data)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (resource_id) DO UPDATE SET
            data = EXCLUDED.data,
            created_time = EXCLUDED.created_time,
            updated_time = EXCLUDED.updated_time,
            created_by = EXCLUDED.created_by,
            updated_by = EXCLUDED.updated_by,
            is_deleted = EXCLUDED.is_deleted,
            schema_version = EXCLUDED.schema_version,
            indexed_data = EXCLUDED.indexed_data
        """

        indexed_data_json = (
            json.dumps(meta.indexed_data, ensure_ascii=False)
            if meta.indexed_data is not UNSET
            else None
        )

        with self.transaction() as cur:
            cur.execute(
                sql,
                (
                    pk,
                    self._serializer.encode(meta),
                    meta.created_time,
                    meta.updated_time,
                    meta.created_by,
                    meta.updated_by,
                    meta.is_deleted,
                    meta.schema_version,
                    indexed_data_json,
                ),
            )

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

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        # 直接从 PostgreSQL 查询

        # 构建查询条件
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
                json_condition, json_params = self._build_condition(condition)
                if json_condition:
                    conditions.append(json_condition)
                    params.extend(json_params)

        # 构建 WHERE 子句
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 构建排序子句
        order_clause = ""
        if query.sorts is not UNSET and query.sorts:
            order_parts = []
            for sort in query.sorts:
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
                    # 使用 JSONB 提取語法對 indexed_data 中的欄位進行排序
                    # PostgreSQL 可以根據 JSON 值的類型自動選擇排序方式
                    # 使用 -> 操作符保持原始類型，讓 PostgreSQL 自動處理不同數據類型的排序
                    jsonb_extract = f"indexed_data->'{sort.field_path}'"
                    order_parts.append(f"{jsonb_extract} {direction}")
            order_clause = "ORDER BY " + ", ".join(order_parts)

        sql = f'SELECT data FROM "{self.table_name}" {where_clause} {order_clause} LIMIT %s OFFSET %s'
        params.append(query.limit)
        params.append(query.offset)

        with self.stream_cursor() as cur:
            cur.execute(sql, params)
            for row in cur:
                yield self._serializer.decode(row["data"])

    def _build_condition(self, condition) -> tuple[str, list]:
        """構建 PostgreSQL 查詢條件 (支援 Meta 欄位與 JSONB 欄位)"""
        from autocrud.types import (
            DataSearchGroup,
            DataSearchLogicOperator,
            DataSearchOperator,
        )

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

        # 判斷是否為 Meta 欄位
        meta_fields = {
            "resource_id",
            "created_time",
            "updated_time",
            "created_by",
            "updated_by",
            "is_deleted",
            "schema_version",
        }

        if field_path in meta_fields:
            column_name = field_path

            if operator == DataSearchOperator.equals:
                return f"{column_name} = %s", [value]
            if operator == DataSearchOperator.not_equals:
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

        if operator == DataSearchOperator.equals:
            if isinstance(value, bool):
                return f"{jsonb_text_extract} = %s", ["true" if value else "false"]
            return f"{jsonb_text_extract} = %s", [str(value)]
        if operator == DataSearchOperator.not_equals:
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
