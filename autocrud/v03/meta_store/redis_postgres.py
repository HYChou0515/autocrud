import redis
import psycopg2 as pg
import psycopg2.pool
from psycopg2.extras import execute_batch, DictCursor
import threading
import atexit
from contextlib import contextmanager
from collections.abc import Generator
from contextlib import suppress
from msgspec import UNSET

from autocrud.v03.basic import (
    Encoding,
    IMetaStore,
    MsgspecSerializer,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSortDirection,
)


class RedisPostgresMetaStore(IMetaStore):
    def __init__(
        self,
        redis_url: str,
        pg_dsn: str,
        encoding: Encoding = Encoding.json,
        sync_interval: int = 1,
    ):
        self._serializer = MsgspecSerializer(
            encoding=encoding, resource_type=ResourceMeta
        )
        self._redis = redis.Redis.from_url(redis_url)
        self._key_prefix = "resource_meta:"
        self._sync_interval = sync_interval
        self._sync_thread = None
        self._stop_sync = threading.Event()

        # 建立連線池（啟動時執行一次）
        self._conn_pool = psycopg2.pool.SimpleConnectionPool(
            minconn=1, maxconn=10, dsn=pg_dsn
        )

        # 初始化 PostgreSQL 表
        self._init_postgres_table()

        # 启动后台同步线程
        self._start_background_sync()

        # 注册退出时的清理函数
        atexit.register(self._cleanup)

    def __del__(self):
        # 物件被回收時自動清理
        with suppress(Exception):
            self._cleanup()

    def _cleanup(self):
        self._stop_sync.set()
        with suppress(Exception):
            if self._sync_thread and self._sync_thread.is_alive():
                self._sync_thread.join(timeout=5)  # 多等幾秒
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
        return self._conn_pool.getconn()

    def put_conn(self, conn):
        self._conn_pool.putconn(conn)

    @contextmanager
    def transaction(self):
        conn = self.get_conn()
        conn.autocommit = False
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
        conn = self.get_conn()  # 取得讀連線
        conn.autocommit = False  # 關閉 autocommit 保證 transaction 手動控制
        try:
            # 建立 server-side cursor (named cursor)
            with conn.cursor(
                name="RedisPostgresMetaStore", cursor_factory=DictCursor
            ) as cur:
                yield cur  # 將 cursor 交給使用者逐筆讀取
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self.put_conn(conn)

    def _init_postgres_table(self):
        """初始化 PostgreSQL 表結構"""
        with self.transaction() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS resource_meta (
                    resource_id TEXT PRIMARY KEY,
                    data BYTEA NOT NULL,
                    created_time TIMESTAMP NOT NULL,
                    updated_time TIMESTAMP NOT NULL,
                    created_by TEXT NOT NULL,
                    updated_by TEXT NOT NULL,
                    is_deleted BOOLEAN NOT NULL
                )
            """)
            # 創建索引
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_time ON resource_meta(created_time)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_updated_time ON resource_meta(updated_time)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_by ON resource_meta(created_by)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_updated_by ON resource_meta(updated_by)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_is_deleted ON resource_meta(is_deleted)"
            )

    def _start_background_sync(self):
        """启动后台同步线程"""
        if self._sync_thread is None or not self._sync_thread.is_alive():
            self._stop_sync.clear()
            self._sync_thread = threading.Thread(
                target=self._background_sync_worker, daemon=True
            )
            self._sync_thread.start()

    def _background_sync_worker(self):
        """后台同步工作线程"""
        while not self._stop_sync.wait(self._sync_interval):
            try:
                self._sync_redis_to_postgres()
            except Exception as e:
                # 记录错误但不中断线程
                print(f"Background sync error: {e}")

    def _get_redis_key(self, pk: str) -> str:
        return f"{self._key_prefix}{pk}"

    def _sync_redis_to_postgres(self):
        """將 Redis 中的所有數據批量同步到 PostgreSQL，然後清空 Redis"""
        pattern = f"{self._key_prefix}*"
        keys = list(self._redis.scan_iter(match=pattern))

        if not keys:
            return

        # 獲取所有數據
        values = self._redis.mget(keys)
        metas = []

        for key, data in zip(keys, values):
            if data:
                meta = self._serializer.decode(data)
                # 從 Redis key 中提取 resource_id
                key_str = key.decode("utf-8") if isinstance(key, bytes) else key
                resource_id = key_str[len(self._key_prefix) :]
                metas.append((resource_id, meta))

        if not metas:
            return

        # 批量插入到 PostgreSQL
        sql = """
        INSERT INTO resource_meta (resource_id, data, created_time, updated_time, created_by, updated_by, is_deleted)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (resource_id) DO UPDATE SET
            data = EXCLUDED.data,
            created_time = EXCLUDED.created_time,
            updated_time = EXCLUDED.updated_time,
            created_by = EXCLUDED.created_by,
            updated_by = EXCLUDED.updated_by,
            is_deleted = EXCLUDED.is_deleted
        """

        with self.transaction() as cur:
            execute_batch(
                cur,
                sql,
                [
                    (
                        resource_id,
                        self._serializer.encode(meta),
                        meta.created_time,
                        meta.updated_time,
                        meta.created_by,
                        meta.updated_by,
                        meta.is_deleted,
                    )
                    for resource_id, meta in metas
                ],
            )

        # 清空 Redis
        if keys:
            self._redis.delete(*keys)

    def force_sync(self):
        """手动触发同步，主要用于测试"""
        self._sync_redis_to_postgres()

    def __getitem__(self, pk: str) -> ResourceMeta:
        # 先檢查 Redis
        redis_key = self._get_redis_key(pk)
        data = self._redis.get(redis_key)
        if data:
            return self._serializer.decode(data)

        # 如果 Redis 中沒有，從 PostgreSQL 查詢
        with self.stream_cursor() as cur:
            cur.execute("SELECT data FROM resource_meta WHERE resource_id = %s", (pk,))
            row = cur.fetchone()
            if row is None:
                raise KeyError(pk)
            return self._serializer.decode(row["data"])

    def __setitem__(self, pk: str, meta: ResourceMeta) -> None:
        # 只寫入 Redis
        redis_key = self._get_redis_key(pk)
        data = self._serializer.encode(meta)
        self._redis.set(redis_key, data)

    def __delitem__(self, pk: str) -> None:
        redis_key = self._get_redis_key(pk)

        # 檢查是否存在於 Redis
        if self._redis.exists(redis_key):
            self._redis.delete(redis_key)
        else:
            # 如果不在 Redis 中，需要從 PostgreSQL 刪除
            with self.transaction() as cur:
                cur.execute("DELETE FROM resource_meta WHERE resource_id = %s", (pk,))
                if cur.rowcount == 0:
                    raise KeyError(pk)

    def __iter__(self) -> Generator[str]:
        # 不再主动同步，依赖后台同步线程
        # 直接从 PostgreSQL 查询所有 resource_id
        with self.stream_cursor() as cur:
            cur.execute("SELECT resource_id FROM resource_meta")
            for row in cur:
                yield row["resource_id"]

    def __len__(self) -> int:
        # 不再主动同步，依赖后台同步线程
        # 直接从 PostgreSQL 计算总数
        with self.stream_cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM resource_meta")
            return cur.fetchone()[0]

    def iter_search(self, query: ResourceMetaSearchQuery) -> Generator[ResourceMeta]:
        self._sync_redis_to_postgres()
        # 不再主动同步，依赖后台同步线程
        # 直接从 PostgreSQL 查询（假设后台已经同步了数据）

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

        # 构建 WHERE 子句
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        # 构建排序子句
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

        sql = f"SELECT data FROM resource_meta {where_clause} {order_clause} LIMIT %s OFFSET %s"
        params.append(query.limit)
        params.append(query.offset)

        with self.stream_cursor() as cur:
            cur.execute(sql, params)
            for row in cur:
                yield self._serializer.decode(row["data"])
