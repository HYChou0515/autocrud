from pathlib import Path

import pytest
from faker import Faker

faker = Faker()

ALL_META_STORE_TYPES = [
    "memory",
    "df",
    "disk",
    "postgres",
    "sql3-mem",
    "sql3-file",
    "sql3-s3",
    "memory-pg",
    "redis",
    "redis-pg",
    "sa-pg",
    "sa-mariadb",
    "sa-mysql",
]


def get_meta_store(store_type: str, tmpdir: Path = None):
    """Get meta store instance."""
    from autocrud.resource_manager.meta_store.df import DFMemoryMetaStore
    from autocrud.resource_manager.meta_store.simple import (
        DiskMetaStore,
        MemoryMetaStore,
    )
    from autocrud.resource_manager.meta_store.sqlite3 import (
        FileSqliteMetaStore,
        MemorySqliteMetaStore,
        S3SqliteMetaStore,
    )

    if store_type == "memory":
        return MemoryMetaStore(encoding="msgpack")
    if store_type == "df":
        return DFMemoryMetaStore(encoding="msgpack")
    if store_type == "disk":
        d = tmpdir / faker.pystr()
        d.mkdir()
        return DiskMetaStore(encoding="msgpack", rootdir=d)
    if store_type == "postgres":
        import psycopg2

        from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

        # Setup PostgreSQL connection
        pg_dsn = "postgresql://admin:password@localhost:5432/your_database"
        try:
            # Reset the test database
            pg_conn = psycopg2.connect(pg_dsn)
            with pg_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS resource_meta;")
                pg_conn.commit()
            pg_conn.close()

            return PostgresMetaStore(pg_dsn=pg_dsn, encoding="msgpack")
        except Exception as e:
            pytest.fail(f"PostgreSQL not available: {e}")

    if store_type == "sql3-mem":
        return MemorySqliteMetaStore(encoding="msgpack")
    if store_type == "sql3-file":
        return FileSqliteMetaStore(
            db_filepath=tmpdir / "test_data_search.db",
            encoding="msgpack",
        )
    if store_type == "sql3-s3":
        # Use real S3/MinIO connection
        import uuid

        test_key = f"test-regex-{uuid.uuid4()}.db"
        try:
            store = S3SqliteMetaStore(
                bucket="test-autocrud",
                key=test_key,
                endpoint_url="http://localhost:9000",
                access_key_id="minioadmin",
                secret_access_key="minioadmin",
                encoding="msgpack",
                auto_sync=False,
                enable_locking=False,
            )
            # 清理函數
            import atexit

            def cleanup():
                try:
                    store.close()
                    import boto3

                    s3 = boto3.client(
                        "s3",
                        endpoint_url="http://localhost:9000",
                        aws_access_key_id="minioadmin",
                        aws_secret_access_key="minioadmin",
                        region_name="us-east-1",
                    )
                    s3.delete_object(Bucket="test-autocrud", Key=test_key)
                except Exception:
                    pass

            atexit.register(cleanup)
            return store
        except Exception as e:
            pytest.fail(f"S3/MinIO not available: {e}")
    if store_type == "memory-pg":
        import psycopg2

        from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
        from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

        # Setup PostgreSQL connection
        pg_dsn = "postgresql://admin:password@localhost:5432/your_database"
        try:
            # Reset the test database
            pg_conn = psycopg2.connect(pg_dsn)
            with pg_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS resource_meta;")
                pg_conn.commit()
            pg_conn.close()

            return FastSlowMetaStore(
                fast_store=MemoryMetaStore(encoding="msgpack"),
                slow_store=PostgresMetaStore(pg_dsn=pg_dsn, encoding="msgpack"),
            )
        except Exception as e:
            pytest.fail(f"PostgreSQL not available: {e}")
    if store_type == "redis":
        import redis

        from autocrud.resource_manager.meta_store.redis import RedisMetaStore

        # Setup Redis connection
        redis_url = "redis://localhost:6379/0"
        try:
            # Reset the test Redis database
            client = redis.Redis.from_url(redis_url)
            client.flushall()
            client.close()

            return RedisMetaStore(
                redis_url=redis_url,
                encoding="msgpack",
                prefix=str(tmpdir).rsplit("/", 1)[-1],
            )
        except Exception as e:
            pytest.fail(f"Redis not available: {e}")
    if store_type == "redis-pg":
        import psycopg2
        import redis

        from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
        from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
        from autocrud.resource_manager.meta_store.redis import RedisMetaStore

        # Setup Redis and PostgreSQL connections
        redis_url = "redis://localhost:6379/0"
        pg_dsn = "postgresql://admin:password@localhost:5432/your_database"

        try:
            # Reset the test Redis database
            client = redis.Redis.from_url(redis_url)
            client.flushall()
            client.close()

            # Reset the test PostgreSQL database
            pg_conn = psycopg2.connect(pg_dsn)
            with pg_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS resource_meta;")
                pg_conn.commit()
            pg_conn.close()

            return FastSlowMetaStore(
                fast_store=RedisMetaStore(
                    redis_url=redis_url,
                    encoding="msgpack",
                    prefix=str(tmpdir).rsplit("/", 1)[-1],
                ),
                slow_store=PostgresMetaStore(pg_dsn=pg_dsn, encoding="msgpack"),
            )
        except Exception as e:
            pytest.fail(f"Redis or PostgreSQL not available: {e}")
    if store_type == "sa-pg":
        import psycopg2

        from autocrud.resource_manager.meta_store.sqlalchemy import (
            SQLAlchemyMetaStore,
        )

        pg_dsn = "postgresql://admin:password@localhost:5432/your_database"
        sa_url = "postgresql+psycopg2://admin:password@localhost:5432/your_database"
        try:
            pg_conn = psycopg2.connect(pg_dsn)
            with pg_conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS resource_meta;")
                pg_conn.commit()
            pg_conn.close()

            return SQLAlchemyMetaStore(url=sa_url, encoding="msgpack")
        except Exception as e:
            pytest.fail(f"PostgreSQL not available: {e}")
    if store_type == "sa-mariadb":
        import pymysql

        from autocrud.resource_manager.meta_store.sqlalchemy import (
            SQLAlchemyMetaStore,
        )

        sa_url = "mysql+pymysql://admin:password@localhost:3306/your_database"
        try:
            conn = pymysql.connect(
                host="localhost",
                port=3306,
                user="admin",
                password="password",
                database="your_database",
            )
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS resource_meta")
            conn.commit()
            conn.close()

            return SQLAlchemyMetaStore(url=sa_url, encoding="msgpack")
        except Exception as e:
            pytest.fail(f"MariaDB not available: {e}")
    if store_type == "sa-mysql":
        import pymysql

        from autocrud.resource_manager.meta_store.sqlalchemy import (
            SQLAlchemyMetaStore,
        )

        sa_url = "mysql+pymysql://admin:password@localhost:3308/your_database"
        try:
            conn = pymysql.connect(
                host="localhost",
                port=3308,
                user="admin",
                password="password",
                database="your_database",
            )
            with conn.cursor() as cur:
                cur.execute("DROP TABLE IF EXISTS resource_meta")
            conn.commit()
            conn.close()

            return SQLAlchemyMetaStore(url=sa_url, encoding="msgpack")
        except Exception as e:
            pytest.fail(f"MySQL not available: {e}")
    raise ValueError(f"Unsupported store_type: {store_type}")
