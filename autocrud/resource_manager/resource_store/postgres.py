"""PostgreSQL-based IResourceStore implementation.

Stores versioned resource data (raw bytes) and revision info in PostgreSQL
tables.  The schema uses two tables:

* ``<table_prefix>resource_data`` – UID-keyed raw data + serialised
  :class:`RevisionInfo`.
* ``<table_prefix>resource_index`` – maps ``(resource_id, revision_id,
  schema_version)`` → UID.

The design mirrors the S3 resource store's UID-based deduplication: if two
revisions share the same UID the underlying bytes are stored only once.
"""

from __future__ import annotations

import io
import time
from collections.abc import Generator, Iterable
from contextlib import contextmanager, suppress
from typing import IO, Any

from autocrud.resource_manager.basic import (
    Encoding,
    IResourceStore,
    MsgspecSerializer,
)
from autocrud.types import RevisionInfo

try:
    import psycopg2
    import psycopg2.pool
    from psycopg2.extras import execute_batch
except ImportError:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]
    execute_batch = None  # type: ignore[assignment]  # ty:ignore[invalid-assignment]


class PostgresResourceStore(IResourceStore):
    """PostgreSQL-backed resource store.

    Args:
        pg_dsn: PostgreSQL connection string
            (e.g. ``"postgresql://user:pass@host:port/db"``).
        encoding: Serialisation format for :class:`RevisionInfo`
            (default ``Encoding.json``).
        table_prefix: Optional prefix for table names, useful to isolate
            multiple tenants / test runs within the same database.
    """

    def __init__(
        self,
        pg_dsn: str,
        encoding: Encoding = Encoding.json,
        *,
        table_prefix: str = "",
    ):
        self._info_serializer = MsgspecSerializer(
            encoding=encoding,
            resource_type=RevisionInfo,
        )

        self._conn_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dsn=pg_dsn,
        )

        self._data_table = f"{table_prefix}resource_data"
        self._index_table = f"{table_prefix}resource_index"

        self._init_tables()

    # ------------------------------------------------------------------
    # Connection helpers (same pattern as PostgresMetaStore)
    # ------------------------------------------------------------------

    def __del__(self):  # pragma: no cover
        with suppress(Exception):
            self._cleanup()

    def _cleanup(self):
        conns: list[Any] = []
        while True:
            try:
                conn = self._conn_pool.getconn(timeout=1)  # ty:ignore[unknown-argument]
                conns.append(conn)
            except Exception:
                break
        for conn in conns:
            with suppress(Exception):
                conn.close()
        with suppress(Exception):
            self._conn_pool.closeall()

    def _get_conn(self) -> Any:
        retry = 5
        last_error: Exception | None = None
        for attempt in range(retry):
            try:
                conn = self._conn_pool.getconn()
            except psycopg2.pool.PoolError:
                last_error = psycopg2.pool.PoolError("connection pool exhausted")
                time.sleep(min(0.5 * (attempt + 1), 3))
                continue

            conn.autocommit = False
            if self._test_query(conn):
                return conn

            try:
                self._conn_pool.putconn(conn, close=True)
            except Exception:
                pass
            last_error = ConnectionError("Failed to get a valid PostgreSQL connection.")
            time.sleep(1)

        if isinstance(last_error, psycopg2.pool.PoolError):
            raise last_error
        raise ConnectionError("Failed to get a valid PostgreSQL connection.")

    def _put_conn(self, conn: Any) -> None:
        self._conn_pool.putconn(conn)

    @staticmethod
    def _test_query(conn: Any) -> bool:
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone()[0] == 1
        except Exception:
            return False

    @contextmanager
    def _transaction(self) -> Generator[Any, None, None]:
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._put_conn(conn)

    # ------------------------------------------------------------------
    # DDL
    # ------------------------------------------------------------------

    def _init_tables(self) -> None:
        with self._transaction() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS "{self._data_table}" (
                    uid TEXT PRIMARY KEY,
                    data BYTEA NOT NULL,
                    info BYTEA NOT NULL
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS "{self._index_table}" (
                    resource_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    schema_version TEXT,
                    uid TEXT NOT NULL REFERENCES "{self._data_table}"(uid),
                    PRIMARY KEY (resource_id, revision_id, schema_version)
                )
            """)
            # Index for fast resource listing / revision listing
            cur.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_{self._index_table}_resource
                ON "{self._index_table}" (resource_id)
            """)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sv(schema_version: str | None) -> str:
        """Normalise schema_version for the composite PK (NULL → '__none__')."""
        return "__none__" if schema_version is None else schema_version

    @staticmethod
    def _unsv(sv: str) -> str | None:
        """Reverse of ``_sv``."""
        return None if sv == "__none__" else sv

    # ------------------------------------------------------------------
    # IResourceStore implementation
    # ------------------------------------------------------------------

    def list_resources(self) -> Generator[str]:
        with self._transaction() as cur:
            cur.execute(f'SELECT DISTINCT resource_id FROM "{self._index_table}"')
            for row in cur.fetchall():
                yield row[0]

    def list_revisions(self, resource_id: str) -> Generator[str]:
        with self._transaction() as cur:
            cur.execute(
                f'SELECT DISTINCT revision_id FROM "{self._index_table}" '
                f"WHERE resource_id = %s",
                (resource_id,),
            )
            for row in cur.fetchall():
                yield row[0]

    def list_schema_versions(
        self, resource_id: str, revision_id: str
    ) -> Generator[str | None]:
        with self._transaction() as cur:
            cur.execute(
                f'SELECT schema_version FROM "{self._index_table}" '
                f"WHERE resource_id = %s AND revision_id = %s",
                (resource_id, revision_id),
            )
            for row in cur.fetchall():
                yield self._unsv(row[0])

    def exists(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> bool:
        with self._transaction() as cur:
            cur.execute(
                f'SELECT 1 FROM "{self._index_table}" '
                f"WHERE resource_id = %s AND revision_id = %s "
                f"AND schema_version = %s",
                (resource_id, revision_id, self._sv(schema_version)),
            )
            return cur.fetchone() is not None

    @contextmanager
    def get_data_bytes(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> Generator[IO[bytes], None, None]:
        with self._transaction() as cur:
            cur.execute(
                f'SELECT d.data FROM "{self._data_table}" d '
                f'JOIN "{self._index_table}" i ON d.uid = i.uid '
                f"WHERE i.resource_id = %s AND i.revision_id = %s "
                f"AND i.schema_version = %s",
                (resource_id, revision_id, self._sv(schema_version)),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(
                    f"Resource not found: {resource_id}/{revision_id}/{schema_version}"
                )
            yield io.BytesIO(bytes(row[0]))

    def get_revision_info(
        self,
        resource_id: str,
        revision_id: str,
        schema_version: str | None,
    ) -> RevisionInfo:
        with self._transaction() as cur:
            cur.execute(
                f'SELECT d.info FROM "{self._data_table}" d '
                f'JOIN "{self._index_table}" i ON d.uid = i.uid '
                f"WHERE i.resource_id = %s AND i.revision_id = %s "
                f"AND i.schema_version = %s",
                (resource_id, revision_id, self._sv(schema_version)),
            )
            row = cur.fetchone()
            if row is None:
                raise KeyError(
                    f"Resource not found: {resource_id}/{revision_id}/{schema_version}"
                )
            return self._info_serializer.decode(bytes(row[0]))

    def save(self, info: RevisionInfo, data: IO[bytes]) -> None:
        uid = str(info.uid)
        raw_data = data.read()
        raw_info = self._info_serializer.encode(info)

        with self._transaction() as cur:
            # Upsert data row
            cur.execute(
                f'INSERT INTO "{self._data_table}" (uid, data, info) '
                f"VALUES (%s, %s, %s) "
                f"ON CONFLICT (uid) DO UPDATE SET data = EXCLUDED.data, info = EXCLUDED.info",
                (uid, raw_data, raw_info),
            )
            # Upsert index row
            cur.execute(
                f'INSERT INTO "{self._index_table}" '
                f"(resource_id, revision_id, schema_version, uid) "
                f"VALUES (%s, %s, %s, %s) "
                f"ON CONFLICT (resource_id, revision_id, schema_version) "
                f"DO UPDATE SET uid = EXCLUDED.uid",
                (
                    info.resource_id,
                    info.revision_id,
                    self._sv(info.schema_version),
                    uid,
                ),
            )

    def save_many(
        self, items: Iterable[tuple[RevisionInfo, bytes | IO[bytes]]]
    ) -> None:
        """Bulk save multiple revisions in a single transaction."""
        item_list = list(items)
        if not item_list:
            return

        with self._transaction() as cur:
            data_rows: list[tuple[str, bytes, bytes]] = []
            index_rows: list[tuple[str, str, str, str]] = []
            for info, data in item_list:
                raw = data.read() if hasattr(data, "read") else data  # ty:ignore[call-non-callable]
                uid = str(info.uid)
                raw_info = self._info_serializer.encode(info)
                data_rows.append((uid, raw, raw_info))
                index_rows.append(
                    (
                        info.resource_id,
                        info.revision_id,
                        self._sv(info.schema_version),
                        uid,
                    )
                )

            execute_batch(
                cur,
                f'INSERT INTO "{self._data_table}" (uid, data, info) '
                f"VALUES (%s, %s, %s) "
                f"ON CONFLICT (uid) DO UPDATE SET data = EXCLUDED.data, info = EXCLUDED.info",
                data_rows,
            )
            execute_batch(
                cur,
                f'INSERT INTO "{self._index_table}" '
                f"(resource_id, revision_id, schema_version, uid) "
                f"VALUES (%s, %s, %s, %s) "
                f"ON CONFLICT (resource_id, revision_id, schema_version) "
                f"DO UPDATE SET uid = EXCLUDED.uid",
                index_rows,
            )

    def purge_resource(self, resource_id: str) -> None:
        """Hard-delete all revision data for a resource."""
        with self._transaction() as cur:
            # Collect UIDs that belong exclusively to this resource
            # (in case of UID deduplication across resources we must not
            # remove data rows still referenced by other resources)
            cur.execute(
                f'SELECT DISTINCT uid FROM "{self._index_table}" '
                f"WHERE resource_id = %s",
                (resource_id,),
            )
            uids = [row[0] for row in cur.fetchall()]

            # Remove index rows first (FK constraint)
            cur.execute(
                f'DELETE FROM "{self._index_table}" WHERE resource_id = %s',
                (resource_id,),
            )

            # Remove data rows only if no other index references them
            for uid in uids:
                cur.execute(
                    f'SELECT 1 FROM "{self._index_table}" WHERE uid = %s LIMIT 1',
                    (uid,),
                )
                if cur.fetchone() is None:
                    cur.execute(
                        f'DELETE FROM "{self._data_table}" WHERE uid = %s',
                        (uid,),
                    )

    def cleanup(self) -> None:
        """Remove all data (both tables). Useful for test teardown."""
        with self._transaction() as cur:
            cur.execute(f'DELETE FROM "{self._index_table}"')
            cur.execute(f'DELETE FROM "{self._data_table}"')

    def drop_tables(self) -> None:
        """Drop both tables. Useful for test teardown."""
        with self._transaction() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{self._index_table}" CASCADE')
            cur.execute(f'DROP TABLE IF EXISTS "{self._data_table}" CASCADE')
