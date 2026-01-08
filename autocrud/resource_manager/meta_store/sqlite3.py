import functools
import json
import pickle
import re
import sqlite3
import threading
import datetime as dt
from collections import defaultdict
from collections.abc import Callable, Generator
from pathlib import Path
from typing import TypeVar

from msgspec import UNSET

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

T = TypeVar("T")


class SqliteMetaStore(ISlowMetaStore):
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
                indexed_data TEXT  -- JSON 格式的索引數據
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

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        import json

        data = self._serializer.encode(meta)
        # 將 indexed_data 轉換為 JSON 字符串
        indexed_data_json = (
            json.dumps(meta.indexed_data, ensure_ascii=False)
            if meta.indexed_data is not UNSET
            else None
        )
        _conn = self._conns[threading.get_ident()]
        _conn.execute(
            """
            INSERT OR REPLACE INTO resource_meta 
            (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted, schema_version, indexed_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pk,
                data,
                meta.created_time.timestamp(),
                meta.updated_time.timestamp(),
                meta.created_by,
                meta.updated_by,
                1 if meta.is_deleted else 0,
                meta.schema_version,
                indexed_data_json,
            ),
        )
        _conn.commit()

    def save_many(self, metas):
        """批量保存元数据到 SQLite（ISlowMetaStore 接口方法）"""
        import json

        if not metas:
            return

        sql = """
        INSERT OR REPLACE INTO resource_meta 
        (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted, schema_version, indexed_data)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        _conn = self._conns[threading.get_ident()]
        with _conn:
            _conn.executemany(
                sql,
                [
                    (
                        meta.resource_id,
                        self._serializer.encode(meta),
                        meta.created_time.timestamp(),
                        meta.updated_time.timestamp(),
                        meta.created_by,
                        meta.updated_by,
                        1 if meta.is_deleted else 0,
                        meta.schema_version,
                        (
                            json.dumps(meta.indexed_data, ensure_ascii=False)
                            if meta.indexed_data is not UNSET
                            else None
                        ),
                    )
                    for meta in metas
                ],
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

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
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

        # 構建 WHERE 子句
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

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
                    json_extract = f"json_extract(indexed_data, '$.{sort.field_path}')"
                    order_parts.append(f"{json_extract} {direction}")
            order_clause = "ORDER BY " + ", ".join(order_parts)

        # 在 SQL 層面應用分頁
        sql = f"SELECT data FROM resource_meta {where_clause} {order_clause} LIMIT ? OFFSET ?"
        params.extend([query.limit, query.offset])

        cursor = self._conns[threading.get_ident()].execute(sql, params)

        for row in cursor:
            yield self._serializer.decode(row[0])

    def _build_condition(self, condition) -> tuple[str, list]:
        """構建 SQLite 查詢條件 (支援 Meta 欄位與 JSON 欄位)"""
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
            # Handle datetime conversion for time fields which are stored as REAL (timestamp)
            if field_path in ("created_time", "updated_time"):
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
                return f"{column_name} = ?", [value]
            if operator == DataSearchOperator.not_equals:
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
        json_extract = f"json_extract(indexed_data, '$.{field_path}')"

        if operator == DataSearchOperator.equals:
            return f"{json_extract} = ?", [value]
        if operator == DataSearchOperator.not_equals:
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
        if operator == DataSearchOperator.is_null:
            if value:
                # Strict is_null: Must exist AND be null
                # json_type returns 'null' if value is null, NULL if missing.
                return f"json_type(indexed_data, '$.{field_path}') = 'null'", []
            else:
                # Strict is_null=False: Must exist AND be NOT null
                # json_type returns type string if exists and not null.
                # So json_type IS NOT NULL AND json_type != 'null'
                return (
                    f"json_type(indexed_data, '$.{field_path}') IS NOT NULL AND json_type(indexed_data, '$.{field_path}') != 'null'",
                    [],
                )
        if operator == DataSearchOperator.exists:
            # json_type returns NULL if key missing, 'null' if value is null
            if value:
                return f"json_type(indexed_data, '$.{field_path}') IS NOT NULL", []
            else:
                return f"json_type(indexed_data, '$.{field_path}') IS NULL", []
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
