import datetime as dt
import functools
import json
import pickle
import re
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable, Generator
from pathlib import Path
from typing import TypeVar

from msgspec import UNSET

from specstar.query_types import (
    AggKeyRef,
    AggSpec,
    DataSearchFilter,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
)
from specstar.resource_manager.basic import (
    Encoding,
    IMetaWithAgg,
    ISlowMetaStore,
    MsgspecSerializer,
)
from specstar.types import ResourceMeta

T = TypeVar("T")


class SqliteMetaStore(IMetaWithAgg, ISlowMetaStore):
    def __init__(
        self,
        *,
        get_conn: Callable[[], sqlite3.Connection],
        encoding: Encoding = Encoding.json,
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=ResourceMeta,
        )
        # Field paths registered as list-typed. ``contains`` on these uses exact
        # element membership (json_each) instead of substring LIKE. See #362.
        self._list_fields: set[str] = set()

        def _get_conn_wrapper():
            conn = get_conn()

            def regexp(expr, item):
                if item is None:
                    return False
                try:
                    return re.search(expr, str(item)) is not None
                except Exception:
                    return False

            conn.create_function("REGEXP", 2, regexp)
            return conn

        self._get_conn = _get_conn_wrapper
        self._conns: dict[int, sqlite3.Connection] = defaultdict(self._get_conn)
        _conn = self._conns[threading.get_ident()]
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_meta (
                resource_id TEXT PRIMARY KEY,
                data BLOB NOT NULL,
                created_time REAL NOT NULL,
                updated_time REAL NOT NULL,
                created_by TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                is_deleted INTEGER NOT NULL,
                schema_version TEXT,
                indexed_data TEXT,  -- JSON 格式的索引數據
                rev_status TEXT,
                rev_created_by TEXT,
                rev_updated_by TEXT,
                rev_created_time REAL,
                rev_updated_time REAL
            )
        """)

        # 檢查是否需要添加 indexed_data 欄位（用於向後兼容）
        cursor = _conn.execute("PRAGMA table_info(resource_meta)")
        columns = [column[1] for column in cursor.fetchall()]
        if "indexed_data" not in columns:
            _conn.execute("ALTER TABLE resource_meta ADD COLUMN indexed_data TEXT")
            _conn.commit()
        if "schema_version" not in columns:
            _conn.execute("ALTER TABLE resource_meta ADD COLUMN schema_version TEXT")
            _conn.commit()
        for col_name, col_type in (
            ("rev_status", "TEXT"),
            ("rev_created_by", "TEXT"),
            ("rev_updated_by", "TEXT"),
            ("rev_created_time", "REAL"),
            ("rev_updated_time", "REAL"),
        ):
            if col_name not in columns:
                _conn.execute(
                    f"ALTER TABLE resource_meta ADD COLUMN {col_name} {col_type}"
                )
                _conn.commit()

        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_time ON resource_meta(created_time)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_updated_time ON resource_meta(updated_time)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_by ON resource_meta(created_by)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_updated_by ON resource_meta(updated_by)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_is_deleted ON resource_meta(is_deleted)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rev_status ON resource_meta(rev_status)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rev_created_by ON resource_meta(rev_created_by)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rev_updated_by ON resource_meta(rev_updated_by)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rev_created_time ON resource_meta(rev_created_time)
        """)
        _conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rev_updated_time ON resource_meta(rev_updated_time)
        """)

        # 遷移已存在的記錄，填充 indexed_data
        self._migrate_existing_data()

        _conn.commit()

    def _migrate_existing_data(self):
        """為已存在但沒有 indexed_data 的記錄填充索引數據"""
        _conn = self._conns[threading.get_ident()]
        cursor = _conn.execute("""
            SELECT resource_id, data FROM resource_meta 
            WHERE indexed_data IS NULL OR indexed_data = ''
        """)

        for resource_id, data_blob in cursor.fetchall():
            try:
                data = pickle.loads(data_blob)
                indexed_data = json.dumps(
                    data.model_dump() if hasattr(data, "model_dump") else data,
                )
                _conn.execute(
                    """
                    UPDATE resource_meta SET indexed_data = ? WHERE resource_id = ?
                """,
                    (indexed_data, resource_id),
                )
            except Exception:
                # 如果解析失敗，設置為空 JSON 對象
                _conn.execute(
                    """
                    UPDATE resource_meta SET indexed_data = '{}' WHERE resource_id = ?
                """,
                    (resource_id,),
                )

    def __getitem__(self, pk: str) -> ResourceMeta:
        _conn = self._conns[threading.get_ident()]
        cursor = _conn.execute(
            "SELECT data FROM resource_meta WHERE resource_id = ?",
            (pk,),
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(pk)
        return self._serializer.decode(row[0])

    def _meta_to_row(self, meta: ResourceMeta) -> tuple:
        """Pack a ResourceMeta into the column-order tuple used by INSERT/UPSERT."""
        import json

        indexed_data_json = (
            json.dumps(meta.indexed_data, ensure_ascii=False)
            if meta.indexed_data is not UNSET
            else None
        )
        return (
            meta.resource_id,
            self._serializer.encode(meta),
            meta.created_time.timestamp(),
            meta.updated_time.timestamp(),
            meta.created_by,
            meta.updated_by,
            1 if meta.is_deleted else 0,
            meta.schema_version,
            indexed_data_json,
            meta.rev_status if meta.rev_status is not UNSET else None,
            meta.rev_created_by if meta.rev_created_by is not UNSET else None,
            meta.rev_updated_by if meta.rev_updated_by is not UNSET else None,
            (
                meta.rev_created_time.timestamp()
                if meta.rev_created_time is not UNSET
                else None
            ),
            (
                meta.rev_updated_time.timestamp()
                if meta.rev_updated_time is not UNSET
                else None
            ),
        )

    _UPSERT_SQL = """
        INSERT OR REPLACE INTO resource_meta
        (resource_id, data, created_time, updated_time, created_by, updated_by,
         is_deleted, schema_version, indexed_data,
         rev_status, rev_created_by, rev_updated_by, rev_created_time, rev_updated_time)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:  # ty:ignore[invalid-method-override]
        _conn = self._conns[threading.get_ident()]
        # ``meta.resource_id`` may differ from ``pk`` only via misuse, but we
        # honour the dict-style key by overriding the first column.
        row = (pk, *self._meta_to_row(meta)[1:])
        _conn.execute(self._UPSERT_SQL, row)
        _conn.commit()

    def save_many(self, metas):
        """批量保存元数据到 SQLite（ISlowMetaStore 接口方法）"""
        if not metas:
            return

        _conn = self._conns[threading.get_ident()]
        with _conn:
            _conn.executemany(
                self._UPSERT_SQL,
                [self._meta_to_row(meta) for meta in metas],
            )

    def __delitem__(self, pk: str) -> None:
        _conn = self._conns[threading.get_ident()]
        cursor = _conn.execute("DELETE FROM resource_meta WHERE resource_id = ?", (pk,))
        if cursor.rowcount == 0:
            raise KeyError(pk)
        _conn.commit()

    def __iter__(self) -> Generator[str]:
        _conn = self._conns[threading.get_ident()]
        cursor = _conn.execute("SELECT resource_id FROM resource_meta")
        for row in cursor:
            yield row[0]

    def __len__(self) -> int:
        _conn = self._conns[threading.get_ident()]
        cursor = _conn.execute("SELECT COUNT(*) FROM resource_meta")
        return cursor.fetchone()[0]

    def register_list_field(self, field_path: str) -> None:
        """Declare *field_path* as a list-typed indexed field.

        Routes ``DataSearchOperator.contains`` on this field through exact
        element membership (``json_each``) instead of the default substring
        ``LIKE``. Idempotent — safe to call from ``add_model`` on every
        registration. See #362.
        """
        self._list_fields.add(field_path)

    def _build_where(self, query: ResourceMetaSearchQuery) -> tuple[str, list]:
        """Translate a search query into a SQL ``WHERE`` clause + params.

        Shared by :meth:`iter_search` and :meth:`aggregate_by` so filtering
        (meta columns + ``indexed_data`` JSON conditions) is built ONE way —
        a pushed-down aggregate filters exactly like a search. Returns the
        ``"WHERE ..."`` string (``""`` when unfiltered) and its param list;
        ordering / paging are the caller's concern.
        """
        conditions = []
        params = []

        if query.is_deleted is not UNSET:
            conditions.append("is_deleted = ?")
            params.append(1 if query.is_deleted else 0)

        if query.created_time_start is not UNSET:
            conditions.append("created_time >= ?")
            params.append(query.created_time_start.timestamp())

        if query.created_time_end is not UNSET:
            conditions.append("created_time <= ?")
            params.append(query.created_time_end.timestamp())

        if query.updated_time_start is not UNSET:
            conditions.append("updated_time >= ?")
            params.append(query.updated_time_start.timestamp())

        if query.updated_time_end is not UNSET:
            conditions.append("updated_time <= ?")
            params.append(query.updated_time_end.timestamp())

        if query.created_bys is not UNSET:
            placeholders = ",".join("?" * len(query.created_bys))
            conditions.append(f"created_by IN ({placeholders})")
            params.extend(query.created_bys)

        if query.updated_bys is not UNSET:
            placeholders = ",".join("?" * len(query.updated_bys))
            conditions.append(f"updated_by IN ({placeholders})")
            params.extend(query.updated_bys)

        if query.rev_statuses is not UNSET:
            placeholders = ",".join("?" * len(query.rev_statuses))
            conditions.append(f"rev_status IN ({placeholders})")
            params.extend(query.rev_statuses)

        if query.rev_created_bys is not UNSET:
            placeholders = ",".join("?" * len(query.rev_created_bys))
            conditions.append(f"rev_created_by IN ({placeholders})")
            params.extend(query.rev_created_bys)

        if query.rev_updated_bys is not UNSET:
            placeholders = ",".join("?" * len(query.rev_updated_bys))
            conditions.append(f"rev_updated_by IN ({placeholders})")
            params.extend(query.rev_updated_bys)

        if query.rev_created_time_start is not UNSET:
            conditions.append("rev_created_time >= ?")
            params.append(query.rev_created_time_start.timestamp())
        if query.rev_created_time_end is not UNSET:
            conditions.append("rev_created_time <= ?")
            params.append(query.rev_created_time_end.timestamp())
        if query.rev_updated_time_start is not UNSET:
            conditions.append("rev_updated_time >= ?")
            params.append(query.rev_updated_time_start.timestamp())
        if query.rev_updated_time_end is not UNSET:
            conditions.append("rev_updated_time <= ?")
            params.append(query.rev_updated_time_end.timestamp())

        # 處理 data_conditions - 在 SQL 層面過濾
        if query.data_conditions is not UNSET:
            for condition in query.data_conditions:
                json_condition, json_params = self._build_condition(condition)
                if json_condition:
                    conditions.append(json_condition)
                    params.extend(json_params)

        # 處理 conditions - 在 SQL 層面過濾
        if query.conditions is not UNSET:
            for condition in query.conditions:
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

        # 構建排序子句
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
                    # 使用 JSON 提取語法對 indexed_data 中的欄位進行排序
                    json_extract = (
                        f"json_extract(indexed_data, '$.\"{sort.field_path}\"')"
                    )
                    order_parts.append(f"{json_extract} {direction}")
            order_clause = "ORDER BY " + ", ".join(order_parts)

        # 在 SQL 層面應用分頁
        sql = f"SELECT data FROM resource_meta {where_clause} {order_clause} LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        cursor = self._conns[threading.get_ident()].execute(sql, params)

        for row in cursor:
            yield self._serializer.decode(row[0])

    def aggregate_by(
        self,
        query: ResourceMetaSearchQuery,
        by: AggKeyRef,
        aggregates: list[AggSpec],
    ) -> list[tuple[object, dict[str, object]]]:
        """Push a ``Count`` group-by down to SQLite — ``GROUP BY`` over the
        filtered set, never materialising one row per match.

        The group key is a real column for ``source="meta"`` or a
        ``json_extract`` of ``indexed_data`` for ``source="data"`` (a missing
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
            "SqliteMetaStore.aggregate_by supports count/sum/min/max"
        )
        if by.source == "meta":
            key_expr = by.name  # a real resource_meta column
        else:
            key_expr = f"json_extract(indexed_data, '$.\"{by.name}\"')"
        where_clause, params = self._build_where(query)
        select_aggs = ", ".join(
            f"{self._agg_expr(a)} AS a{i}" for i, a in enumerate(aggregates)
        )
        sql = (
            f"SELECT {key_expr} AS k, {select_aggs} "
            f"FROM resource_meta {where_clause} GROUP BY {key_expr}"
        )
        cursor = self._conns[threading.get_ident()].execute(sql, params)
        return [
            (row[0], {a.result_name: row[i + 1] for i, a in enumerate(aggregates)})
            for row in cursor
        ]

    def _agg_expr(self, a: AggSpec) -> str:
        """SQL for one aggregate's value (not the GROUP BY key). ``Count``
        ignores the field; a value reducer reads a ``resource_meta`` column
        (``source="meta"``) or ``json_extract(indexed_data, …)``
        (``source="data"``). The time columns are stored as ``REAL`` Unix
        epochs, so ``MIN``/``MAX`` over a ``value_type="datetime"`` meta column
        already yield an epoch the ResourceManager turns back into a UTC
        datetime — no special expression needed on SQLite. A field-less
        ``count`` is ``COUNT(*)``; a ``count`` WITH a field counts that field's
        non-null values (the denominator for a decomposed ``Avg``)."""
        if a.op == "count" and a.field is None:
            return "COUNT(*)"
        ref = a.field
        assert ref is not None, "value reducer requires a field"
        if ref.source == "meta":
            val = ref.name
        else:
            val = f"json_extract(indexed_data, '$.\"{ref.name}\"')"
        return f"{a.op.upper()}({val})"

    def _build_condition(self, condition: DataSearchFilter) -> tuple[str, list]:
        """構建 SQLite 查詢條件 (支援 Meta 欄位與 JSON 欄位)"""
        from specstar.query_types import (
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
                return f"NOT ({' AND '.join(sub_conditions)})", sub_params
            return "", []

        field_path = condition.field_path
        operator = condition.operator
        value = condition.value

        # Normalize Enum to value (indexed data stores Enum as value string)
        from enum import Enum as EnumType

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
            # Handle datetime conversion for time fields which are stored as REAL (timestamp)
            if field_path in (
                "created_time",
                "updated_time",
                "rev_created_time",
                "rev_updated_time",
            ):
                if isinstance(value, dt.datetime):
                    value = value.timestamp()
                elif isinstance(value, (list, tuple, set)):
                    value = [
                        v.timestamp() if isinstance(v, dt.datetime) else v
                        for v in value
                    ]

            # 直接使用欄位名稱
            column_name = field_path

            if operator == DataSearchOperator.equals:
                # Handle list/dict comparison for meta fields
                if isinstance(value, (list, dict)):
                    # Cannot compare meta fields to list/dict, skip this condition
                    return "", []
                return f"{column_name} = ?", [value]
            if operator == DataSearchOperator.not_equals:
                # Handle list/dict comparison for meta fields
                if isinstance(value, (list, dict)):
                    # Meta field is never equal to list/dict, skip this condition
                    return "", []
                return f"{column_name} != ?", [value]
            if operator == DataSearchOperator.greater_than:
                return f"{column_name} > ?", [value]
            if operator == DataSearchOperator.greater_than_or_equal:
                return f"{column_name} >= ?", [value]
            if operator == DataSearchOperator.less_than:
                return f"{column_name} < ?", [value]
            if operator == DataSearchOperator.less_than_or_equal:
                return f"{column_name} <= ?", [value]
            if operator == DataSearchOperator.contains:
                return f"{column_name} LIKE ?", [f"%{value}%"]
            if operator == DataSearchOperator.starts_with:
                return f"{column_name} LIKE ?", [f"{value}%"]
            if operator == DataSearchOperator.ends_with:
                return f"{column_name} LIKE ?", [f"%{value}"]
            if operator == DataSearchOperator.regex:
                return f"{column_name} REGEXP ?", [value]
            if operator == DataSearchOperator.in_list:
                if isinstance(value, (list, tuple, set)):
                    placeholders = ",".join("?" * len(value))
                    return f"{column_name} IN ({placeholders})", list(value)
            elif operator == DataSearchOperator.not_in_list:
                if isinstance(value, (list, tuple, set)):
                    placeholders = ",".join("?" * len(value))
                    return f"{column_name} NOT IN ({placeholders})", list(value)
            if operator == DataSearchOperator.is_null:
                if value:
                    return f"{column_name} IS NULL", []
                else:
                    return f"{column_name} IS NOT NULL", []
            # Meta fields always exist, so exists=True is always True, exists=False is always False
            if operator == DataSearchOperator.exists:
                if value:
                    return "1=1", []
                else:
                    return "1=0", []
            # isna for meta fields is same as is_null
            if operator == DataSearchOperator.isna:
                if value:
                    return f"{column_name} IS NULL", []
                else:
                    return f"{column_name} IS NOT NULL", []

            # Fallback or unsupported operator for meta fields
            return "", []

        # SQLite JSON 提取語法: json_extract(indexed_data, '$.field_path')
        json_extract = f"json_extract(indexed_data, '$.\"{field_path}\"')"

        # Apply field transformation if specified
        if condition.transform is not None:
            from specstar.query_types import FieldTransform

            if condition.transform == FieldTransform.length:
                # Get length of JSON value (works for strings and arrays)
                # Use json_array_length for arrays, length() for strings
                # SQLite's length() returns NULL for non-string types, so we need type checking
                json_type = f"json_type(indexed_data, '$.\"{field_path}\"')"
                # For arrays: use json_array_length
                # For strings: use length()
                # For others: return NULL
                json_extract = f"""CASE 
                    WHEN {json_type} = 'array' THEN json_array_length(indexed_data, '$.\"{field_path}\"')
                    WHEN {json_type} = 'text' THEN length({json_extract})
                    ELSE NULL
                END"""

        if operator == DataSearchOperator.equals:
            # Handle list/dict comparison for JSON fields
            if isinstance(value, (list, dict)):
                # For list/dict, we need JSON comparison
                import json

                return f"{json_extract} = json(?)", [
                    json.dumps(value, ensure_ascii=False)
                ]
            return f"{json_extract} = ?", [value]
        if operator == DataSearchOperator.not_equals:
            # Handle list/dict comparison for JSON fields
            if isinstance(value, (list, dict)):
                # For list/dict, we need JSON comparison
                import json

                # NULL safe comparison: field != value OR field IS NULL
                return f"({json_extract} != json(?) OR {json_extract} IS NULL)", [
                    json.dumps(value, ensure_ascii=False)
                ]
            return f"{json_extract} != ?", [value]
        if operator == DataSearchOperator.greater_than:
            return f"CAST({json_extract} AS REAL) > ?", [value]
        if operator == DataSearchOperator.greater_than_or_equal:
            return f"CAST({json_extract} AS REAL) >= ?", [value]
        if operator == DataSearchOperator.less_than:
            return f"CAST({json_extract} AS REAL) < ?", [value]
        if operator == DataSearchOperator.less_than_or_equal:
            return f"CAST({json_extract} AS REAL) <= ?", [value]
        if operator == DataSearchOperator.contains:
            # List-typed fields use exact element membership (json_each) so
            # ``contains`` isn't a substring on the serialised JSON array — which
            # produced false-positives like "c1" matching ["c10"]. String fields
            # keep LIKE substring semantics. See #362.
            if field_path in self._list_fields:
                return (
                    f"EXISTS (SELECT 1 FROM "
                    f"json_each(indexed_data, '$.\"{field_path}\"') WHERE value = ?)",
                    [value],
                )
            return f"{json_extract} LIKE ?", [f"%{value}%"]
        if operator == DataSearchOperator.starts_with:
            return f"{json_extract} LIKE ?", [f"{value}%"]
        if operator == DataSearchOperator.ends_with:
            return f"{json_extract} LIKE ?", [f"%{value}"]
        if operator == DataSearchOperator.regex:
            return f"{json_extract} REGEXP ?", [value]
        if operator == DataSearchOperator.in_list:
            if isinstance(value, (list, tuple, set)):
                placeholders = ",".join("?" * len(value))
                return f"{json_extract} IN ({placeholders})", list(value)
        elif operator == DataSearchOperator.not_in_list:
            if isinstance(value, (list, tuple, set)):
                placeholders = ",".join("?" * len(value))
                return f"{json_extract} NOT IN ({placeholders})", list(value)
        if operator == DataSearchOperator.contains_any:
            # List set-overlap: unnest the array (json_each) and test element
            # membership against the candidate set — exact, unlike the LIKE hack
            # `contains` uses. json_each yields one row for a scalar too, so this
            # degrades to membership on a scalar field (matching the Python path).
            vals = list(value) if isinstance(value, (list, tuple, set)) else [value]
            if not vals:
                return "1=0", []  # empty candidate set matches nothing
            placeholders = ",".join("?" * len(vals))
            return (
                f"EXISTS (SELECT 1 FROM json_each(indexed_data, '$.\"{field_path}\"') "
                f"WHERE value IN ({placeholders}))",
                vals,
            )
        if operator == DataSearchOperator.is_null:
            if value:
                # Strict is_null: Must exist AND be null
                # json_type returns 'null' if value is null, NULL if missing.
                return f"json_type(indexed_data, '$.\"{field_path}\"') = 'null'", []
            else:
                # Strict is_null=False: Must exist AND be NOT null
                # json_type returns type string if exists and not null.
                # So json_type IS NOT NULL AND json_type != 'null'
                return (
                    f"json_type(indexed_data, '$.\"{field_path}\"') IS NOT NULL AND json_type(indexed_data, '$.\"{field_path}\"') != 'null'",
                    [],
                )
        if operator == DataSearchOperator.exists:
            # json_type returns NULL if key missing, 'null' if value is null
            if value:
                return f"json_type(indexed_data, '$.\"{field_path}\"') IS NOT NULL", []
            else:
                return f"json_type(indexed_data, '$.\"{field_path}\"') IS NULL", []
        if operator == DataSearchOperator.isna:
            if value:
                return f"{json_extract} IS NULL", []
            else:
                return f"{json_extract} IS NOT NULL", []

        # 如果不支持的操作，返回空條件
        return "", []


class FileSqliteMetaStore(SqliteMetaStore):
    def __init__(self, *, db_filepath: Path, encoding=Encoding.json):
        get_conn = functools.partial(sqlite3.connect, db_filepath)
        super().__init__(get_conn=get_conn, encoding=encoding)


class MemorySqliteMetaStore(SqliteMetaStore):
    def __init__(self, *, encoding=Encoding.json):
        get_conn = functools.partial(sqlite3.connect, ":memory:")
        super().__init__(get_conn=get_conn, encoding=encoding)


class S3ConflictError(Exception):
    """Raised when S3 ETag conflict is detected during sync"""

    pass


class S3SqliteMetaStore(SqliteMetaStore):
    """SQLite Meta Store with S3 backend storage

    Downloads the SQLite database from S3 on initialization,
    operates on local copy, and syncs back to S3 when needed.

    Uses ETag-based optimistic locking to prevent concurrent write conflicts.
    """

    # Constants
    _READ_CHECK_INTERVAL_SECONDS = 1.0  # Check S3 ETag at most once per second
    _S3_NOT_FOUND_CODES = ("404", "NoSuchKey")

    def __init__(
        self,
        *,
        bucket: str,
        key: str,
        access_key_id: str = "minioadmin",
        secret_access_key: str = "minioadmin",
        region_name: str = "us-east-1",
        endpoint_url: str | None = None,
        encoding: Encoding = Encoding.json,
        auto_sync: bool = True,
        sync_interval: float = 0,  # Sync interval in seconds (0 = immediate)
        enable_locking: bool = True,  # Enable ETag-based locking
        auto_reload_on_conflict: bool = False,  # Auto reload from S3 on conflict
        check_etag_on_read: bool = True,  # Check ETag before read operations
    ):
        """Initialize S3 SQLite Meta Store

        Args:
            bucket: S3 bucket name
            key: S3 object key for the database file
            access_key_id: AWS access key ID
            secret_access_key: AWS secret access key
            region_name: AWS region name
            endpoint_url: Custom endpoint URL (for MinIO, LocalStack, etc.)
            encoding: Encoding format (json or msgpack)
            auto_sync: Whether to automatically sync to S3
            sync_interval: Time interval in seconds between syncs (0 = immediate, default)
            enable_locking: Enable ETag-based optimistic locking
            auto_reload_on_conflict: Automatically reload from S3 on conflict
            check_etag_on_read: Check and reload if S3 version changed before reads
        """
        import tempfile
        import time

        import boto3
        from botocore.exceptions import ClientError

        self.bucket = bucket
        self.key = key
        self.auto_sync = auto_sync
        self.sync_interval = sync_interval
        self.enable_locking = enable_locking
        self.auto_reload_on_conflict = auto_reload_on_conflict
        self._check_etag_on_read = check_etag_on_read
        self._current_etag: str | None = None
        self._last_sync_time: float = 0
        self._last_read_check_time: float = 0

        # Initialize S3 client
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region_name,
        )

        # Create temporary file for local database
        self._temp_file = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".db",
        )
        self._db_filepath = Path(self._temp_file.name)
        self._temp_file.close()

        # Try to download existing database from S3
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=self.key)
            # Save the ETag for optimistic locking
            self._current_etag = response.get("ETag")
            # Download the file content
            with open(self._db_filepath, "wb") as f:
                f.write(response["Body"].read())
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code")
            if error_code == "404" or error_code == "NoSuchKey":
                # Database doesn't exist in S3 yet, will be created locally
                self._current_etag = None
            else:
                raise

        # Initialize with local database file
        get_conn = functools.partial(
            sqlite3.connect, self._db_filepath, check_same_thread=False
        )
        super().__init__(get_conn=get_conn, encoding=encoding)

        self._last_sync_time = time.time()
        self._last_read_check_time = time.time()

    @staticmethod
    def _is_s3_not_found_error(client_error) -> bool:
        """Check if ClientError is a 404/NoSuchKey error"""
        error_code = client_error.response.get("Error", {}).get("Code")
        return error_code in S3SqliteMetaStore._S3_NOT_FOUND_CODES

    @staticmethod
    def _create_empty_database(db_path: Path):
        """Create an empty SQLite database with proper schema"""
        db_path.unlink(missing_ok=True)
        conn = sqlite3.connect(db_path)

        # Create table with full schema
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resource_meta (
                resource_id TEXT PRIMARY KEY,
                data BLOB NOT NULL,
                created_time REAL NOT NULL,
                updated_time REAL NOT NULL,
                created_by TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                is_deleted INTEGER NOT NULL,
                schema_version TEXT,
                indexed_data TEXT,
                rev_status TEXT,
                rev_created_by TEXT,
                rev_updated_by TEXT,
                rev_created_time REAL,
                rev_updated_time REAL
            )
            """
        )

        # Create indexes
        for field in (
            "created_time",
            "updated_time",
            "created_by",
            "updated_by",
            "is_deleted",
            "rev_status",
            "rev_created_by",
            "rev_updated_by",
            "rev_created_time",
            "rev_updated_time",
        ):
            conn.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{field} ON resource_meta({field})"
            )

        conn.commit()
        conn.close()

    def _check_and_reload_if_needed(self):
        """Check S3 ETag before read and reload if changed"""
        if not self._check_etag_on_read or not self.enable_locking:
            return

        import time

        from botocore.exceptions import ClientError

        # Only check periodically to avoid too many API calls
        current_time = time.time()
        if (
            current_time - self._last_read_check_time
            < self._READ_CHECK_INTERVAL_SECONDS
        ):
            return

        self._last_read_check_time = current_time

        try:
            head_response = self.s3_client.head_object(Bucket=self.bucket, Key=self.key)
            s3_etag = head_response.get("ETag")

            if s3_etag != self._current_etag:
                self._reload_from_s3()
        except ClientError:
            # Silently ignore errors during read check to avoid blocking reads
            # This includes 404 (file deleted) and other S3 errors
            pass

    def _maybe_sync(self):
        """Sync to S3 if auto_sync is enabled and interval reached"""
        if not self.auto_sync:
            return

        import time

        current_time = time.time()

        # sync_interval = 0 means immediate sync (default)
        if self.sync_interval == 0:
            self.sync_to_s3()
            self._last_sync_time = current_time
        elif current_time - self._last_sync_time >= self.sync_interval:
            self.sync_to_s3()
            self._last_sync_time = current_time

    def _check_etag_conflict(self):
        """Check for ETag conflict and handle according to settings

        Raises:
            S3ConflictError: If conflict detected and auto_reload is disabled
        """
        from botocore.exceptions import ClientError

        try:
            head_response = self.s3_client.head_object(Bucket=self.bucket, Key=self.key)
            current_s3_etag = head_response.get("ETag")

            if current_s3_etag != self._current_etag:
                if self.auto_reload_on_conflict:
                    self._reload_from_s3()
                    raise S3ConflictError(
                        f"S3 object was modified by another process. "
                        f"Expected ETag: {self._current_etag}, "
                        f"Current ETag: {current_s3_etag}. "
                        f"Database reloaded from S3. Local changes were discarded."
                    )
                else:
                    raise S3ConflictError(
                        f"S3 object was modified by another process. "
                        f"Expected ETag: {self._current_etag}, "
                        f"Current ETag: {current_s3_etag}. "
                        f"Sync aborted to prevent data loss."
                    )
        except ClientError as e:
            if not self._is_s3_not_found_error(e):
                raise

    def sync_to_s3(self, force: bool = False):
        """Manually sync local database to S3

        Args:
            force: If True, bypass ETag check and force upload

        Raises:
            S3ConflictError: If ETag conflict detected (another instance modified the file)
        """
        # Ensure all connections are committed
        for conn in self._conns.values():
            conn.commit()

        try:
            # Check for conflicts if locking is enabled
            if self.enable_locking and self._current_etag and not force:
                self._check_etag_conflict()

            # Upload the file
            extra_args = {"Metadata": {"uploaded-by": "specstar"}}
            self.s3_client.upload_file(
                str(self._db_filepath), self.bucket, self.key, ExtraArgs=extra_args
            )

            # Update ETag after successful upload
            head_response = self.s3_client.head_object(Bucket=self.bucket, Key=self.key)
            self._current_etag = head_response.get("ETag")

        except S3ConflictError:
            raise
        except Exception as e:
            raise RuntimeError(f"Failed to sync to S3: {e}") from e

    def __getitem__(self, pk: str) -> ResourceMeta:
        """Get resource metadata, checking S3 for updates first if enabled"""
        self._check_and_reload_if_needed()
        return super().__getitem__(pk)

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        super().__setitem__(pk, meta)
        self._maybe_sync()

    def __delitem__(self, pk: str) -> None:
        super().__delitem__(pk)
        self._maybe_sync()

    def __iter__(self):
        """Iterate over resource IDs, checking S3 for updates first if enabled"""
        self._check_and_reload_if_needed()
        return super().__iter__()

    def iter_search(self, query):
        """Search resources, checking S3 for updates first if enabled"""
        self._check_and_reload_if_needed()
        return super().iter_search(query)

    def save_many(self, metas):
        super().save_many(metas)
        self._maybe_sync()

    def close(self):
        """Close all connections and sync to S3"""
        # Sync before closing
        if self.auto_sync:
            self.sync_to_s3()

        # Close all connections
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()

    def _reload_from_s3(self):
        """Reload database from S3, discarding local changes (private method)"""
        from botocore.exceptions import ClientError

        # Close existing connections
        for conn in self._conns.values():
            conn.close()
        self._conns.clear()

        # Download fresh copy from S3
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=self.key)
            self._current_etag = response.get("ETag")
            with open(self._db_filepath, "wb") as f:
                f.write(response["Body"].read())
        except ClientError as e:
            if self._is_s3_not_found_error(e):
                # File doesn't exist anymore, create empty database
                self._current_etag = None
                self._create_empty_database(self._db_filepath)
            else:
                raise

    def __del__(self):
        """Cleanup: sync to S3 and remove temporary file"""
        try:
            self.close()
        except Exception:
            pass

        # Remove temporary file
        try:
            self._db_filepath.unlink()
        except Exception:
            pass
