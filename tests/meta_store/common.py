from pathlib import Path

import pytest
from faker import Faker

faker = Faker()

ALL_META_STORE_TYPES = [
    "memory",
    # "df",
    "disk",
    "postgres",
    "sql3-mem",
    # "sql3-file",
    "sql3-s3",
    # "memory-pg",
    "redis",
    # "redis-pg",
    # "sa-pg",
    # "sa-mariadb",
    # "sa-mysql",
    # "sa-sqlite",
    # "sa-oracle",
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
                cur.execute("DROP TABLE IF EXISTS resource_meta CASCADE;")
                cur.execute("DROP TYPE IF EXISTS resource_meta CASCADE;")
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
                cur.execute("DROP TABLE IF EXISTS resource_meta CASCADE;")
                cur.execute("DROP TYPE IF EXISTS resource_meta CASCADE;")
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
                cur.execute("DROP TABLE IF EXISTS resource_meta CASCADE;")
                cur.execute("DROP TYPE IF EXISTS resource_meta CASCADE;")
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
                cur.execute("DROP TABLE IF EXISTS resource_meta CASCADE;")
                cur.execute("DROP TYPE IF EXISTS resource_meta CASCADE;")
                pg_conn.commit()
            pg_conn.close()

            engine_kwargs = {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
            return SQLAlchemyMetaStore(
                url=sa_url, encoding="msgpack", engine_kwargs=engine_kwargs
            )
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

            engine_kwargs = {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
            return SQLAlchemyMetaStore(
                url=sa_url, encoding="msgpack", engine_kwargs=engine_kwargs
            )
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

            engine_kwargs = {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_pre_ping": True,
                "pool_recycle": 3600,
            }
            return SQLAlchemyMetaStore(
                url=sa_url, encoding="msgpack", engine_kwargs=engine_kwargs
            )
        except Exception as e:
            pytest.fail(f"MySQL not available: {e}")
    if store_type == "sa-sqlite":
        from autocrud.resource_manager.meta_store.sqlalchemy import (
            SQLAlchemyMetaStore,
        )

        # Use file-based SQLite for testing
        db_file = tmpdir / "test_sa_sqlite.db"
        sa_url = f"sqlite:///{db_file}"
        try:
            return SQLAlchemyMetaStore(url=sa_url, encoding="msgpack")
        except Exception as e:
            pytest.fail(f"SQLite not available: {e}")
    if store_type == "sa-oracle":
        import oracledb

        from autocrud.resource_manager.meta_store.sqlalchemy import (
            SQLAlchemyMetaStore,
        )

        sa_url = (
            "oracle+oracledb://admin:password@localhost:1522/?service_name=FREEPDB1"
        )

        # Add connection pool configuration to prevent connection exhaustion
        engine_kwargs = {
            "pool_size": 5,
            "max_overflow": 10,
            "pool_pre_ping": True,  # Verify connections before using
            "pool_recycle": 3600,  # Recycle connections after 1 hour
        }

        try:
            # Clean up test table using direct connection with retry
            import time

            max_retries = 3
            retry_delay = 2

            for attempt in range(max_retries):
                try:
                    conn = oracledb.connect(
                        user="admin",
                        password="password",
                        host="localhost",
                        port=1522,
                        service_name="FREEPDB1",
                    )
                    with conn.cursor() as cur:
                        try:
                            cur.execute("DROP TABLE resource_meta")
                        except Exception:
                            pass  # Table might not exist
                    conn.commit()
                    conn.close()
                    break  # Success, exit retry loop
                except oracledb.OperationalError as e:
                    if "DPY-6000" in str(e) and attempt < max_retries - 1:
                        # Connection pool full, wait and retry
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                        continue
                    raise  # Re-raise if not retryable or last attempt

            return SQLAlchemyMetaStore(
                url=sa_url, encoding="msgpack", engine_kwargs=engine_kwargs
            )
        except Exception as e:
            pytest.fail(f"Oracle not available: {e}")
    raise ValueError(f"Unsupported store_type: {store_type}")
