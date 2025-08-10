from collections import defaultdict
from collections.abc import Callable, Generator
import functools
from pathlib import Path
import sqlite3
import threading
from typing import TypeVar
from msgspec import UNSET

from autocrud.v03.resource_manager.basic import (
    Encoding,
    ISlowMetaStore,
    MsgspecSerializer,
    ResourceMeta,
    ResourceMetaSearchQuery,
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
            encoding=encoding, resource_type=ResourceMeta
        )
        self._get_conn = get_conn
        self._conns: dict[int, sqlite3.Connection] = defaultdict(self._get_conn)
        _conn = self._conns[threading.get_ident()]
        _conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_meta (
                resource_id TEXT PRIMARY KEY,
                data BLOB NOT NULL,
                created_time TEXT NOT NULL,
                updated_time TEXT NOT NULL,
                created_by TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                is_deleted INTEGER NOT NULL
            )
        """)
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

    def __getitem__(self, pk: str) -> ResourceMeta:
        _conn = self._conns[threading.get_ident()]
        cursor = _conn.execute(
            "SELECT data FROM resource_meta WHERE resource_id = ?", (pk,)
        )
        row = cursor.fetchone()
        if row is None:
            raise KeyError(pk)
        return self._serializer.decode(row[0])

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        data = self._serializer.encode(meta)
        _conn = self._conns[threading.get_ident()]
        _conn.execute(
            """
            INSERT OR REPLACE INTO resource_meta 
            (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                pk,
                data,
                meta.created_time.isoformat(),
                meta.updated_time.isoformat(),
                meta.created_by,
                meta.updated_by,
                1 if meta.is_deleted else 0,
            ),
        )
        _conn.commit()

    def save_many(self, metas):
        """批量保存元数据到 SQLite（ISlowMetaStore 接口方法）"""
        if not metas:
            return

        sql = """
        INSERT OR REPLACE INTO resource_meta 
        (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        _conn = self._conns[threading.get_ident()]
        with _conn:
            _conn.executemany(
                sql,
                [
                    (
                        meta.resource_id,
                        self._serializer.encode(meta),
                        meta.created_time.isoformat(),
                        meta.updated_time.isoformat(),
                        meta.created_by,
                        meta.updated_by,
                        1 if meta.is_deleted else 0,
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
            params.append(query.created_time_start.isoformat())

        if query.created_time_end is not UNSET:
            conditions.append("created_time <= ?")
            params.append(query.created_time_end.isoformat())

        if query.updated_time_start is not UNSET:
            conditions.append("updated_time >= ?")
            params.append(query.updated_time_start.isoformat())

        if query.updated_time_end is not UNSET:
            conditions.append("updated_time <= ?")
            params.append(query.updated_time_end.isoformat())

        if query.created_bys is not UNSET:
            placeholders = ",".join("?" * len(query.created_bys))
            conditions.append(f"created_by IN ({placeholders})")
            params.extend(query.created_bys)

        if query.updated_bys is not UNSET:
            placeholders = ",".join("?" * len(query.updated_bys))
            conditions.append(f"updated_by IN ({placeholders})")
            params.extend(query.updated_bys)

        # 構建 WHERE 子句
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 構建排序子句
        order_clause = ""
        if query.sorts is not UNSET and query.sorts:
            order_parts = []
            for sort in query.sorts:
                direction = (
                    "ASC"
                    if sort.direction == ResourceMetaSortDirection.ascending
                    else "DESC"
                )
                order_parts.append(f"{sort.key} {direction}")
            order_clause = "ORDER BY " + ", ".join(order_parts)

        sql = f"SELECT data FROM resource_meta {where_clause} {order_clause} LIMIT ? OFFSET ?"
        params.append(query.limit)
        params.append(query.offset)
        cursor = self._conns[threading.get_ident()].execute(sql, params)

        for row in cursor:
            yield self._serializer.decode(row[0])


class FileSqliteMetaStore(SqliteMetaStore):
    def __init__(self, *, db_filepath: Path, encoding=Encoding.json):
        get_conn = functools.partial(sqlite3.connect, db_filepath)
        super().__init__(get_conn=get_conn, encoding=encoding)


class MemorySqliteMetaStore(SqliteMetaStore):
    def __init__(self, *, encoding=Encoding.json):
        get_conn = functools.partial(sqlite3.connect, ":memory:")
        super().__init__(get_conn=get_conn, encoding=encoding)
