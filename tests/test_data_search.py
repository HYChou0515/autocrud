import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from msgspec import UNSET

from autocrud.types import (
    ResourceMetaSortDirection,
)
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceDataSearchSort,
    ResourceMeta,
    ResourceMetaSearchQuery,
)


@dataclass
class User:
    name: str
    email: str
    age: int
    department: str


@dataclass
class Product:
    name: str
    price: float
    category: str
    tags: list[str]


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.parametrize(
    "meta_store_type",
    [
        "memory",
        "sql3-mem",
        "sql3-file",
        "memory-pg",
        "redis",
        "redis-pg",  # FastSlowMetaStore with Redis + PostgreSQL
    ],
)
class TestMetaStoreIterSearch:
    """Test IMetaStore.iter_search method with different storage types."""

    @pytest.fixture(autouse=True)
    def setup_method(self, meta_store_type, my_tmpdir):
        self.meta_store = self._get_meta_store(meta_store_type, my_tmpdir)
        sample_metas = self._create_sample_resource_metas(self.meta_store)

    def test_iter_search_department_filter(self):
        """Test using IMetaStore.iter_search directly for department filtering."""
        # Search for Engineering department users
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="department",
                    operator=DataSearchOperator.equals,
                    value="Engineering",
                ),
            ],
            sorts=[
                ResourceDataSearchSort(
                    field_path="age",
                    direction=ResourceMetaSortDirection.ascending,
                ),
            ],
            limit=10,
            offset=0,
        )

        # 直接使用 MetaStore 的 iter_search
        results = list(self.meta_store.iter_search(query))

        # Should find 3 Engineering users (Alice, Charlie, Eve)
        assert len(results) == 3
        engineering_names = []
        for meta in results:
            engineering_names.append(meta.indexed_data["name"])
            # Verify indexed data is populated
            assert meta.indexed_data is not UNSET
            assert meta.indexed_data["department"] == "Engineering"
        assert engineering_names == ["Alice", "Eve", "Charlie"]

    def test_iter_search_age_range(self):
        """Test using IMetaStore.iter_search for age range filtering."""
        # Search for users aged 30 or older
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="age",
                    operator=DataSearchOperator.greater_than_or_equal,
                    value=30,
                ),
            ],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 3 users (Bob: 30, Charlie: 35, Eve: 32)
        assert len(results) == 3
        ages = []
        for meta in results:
            ages.append(meta.indexed_data["age"])
            assert meta.indexed_data["age"] >= 30
        assert sorted(ages) == [30, 32, 35]

    def test_iter_search_combined_conditions(self):
        """Test using IMetaStore.iter_search with multiple combined conditions."""
        # Search for Engineering users under age 35
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="department",
                    operator=DataSearchOperator.equals,
                    value="Engineering",
                ),
                DataSearchCondition(
                    field_path="age",
                    operator=DataSearchOperator.less_than,
                    value=35,
                ),
            ],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 2 users (Alice: 25, Eve: 32) - Charlie is 35 so excluded
        assert len(results) == 2
        engineering_under_35 = set()
        for meta in results:
            engineering_under_35.add(meta.indexed_data["name"])
            assert meta.indexed_data["department"] == "Engineering"
            assert meta.indexed_data["age"] < 35
        assert engineering_under_35 == {"Alice", "Eve"}

    def _get_meta_store(self, store_type: str, tmpdir):
        """Get meta store instance."""
        from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
        from autocrud.resource_manager.meta_store.sqlite3 import (
            FileSqliteMetaStore,
            MemorySqliteMetaStore,
        )

        if store_type == "memory":
            return MemoryMetaStore(encoding="msgpack")
        if store_type == "sql3-mem":
            return MemorySqliteMetaStore(encoding="msgpack")
        if store_type == "sql3-file":
            return FileSqliteMetaStore(
                db_filepath=tmpdir / "test_data_search.db",
                encoding="msgpack",
            )
        if store_type == "memory-pg":
            import psycopg2

            from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
            from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore

            # Setup PostgreSQL connection
            pg_dsn = (
                "postgresql://postgres:mysecretpassword@localhost:5432/your_database"
            )
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
                pytest.skip(f"PostgreSQL not available: {e}")
        elif store_type == "redis":
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
                pytest.skip(f"Redis not available: {e}")
        elif store_type == "redis-pg":
            import psycopg2
            import redis

            from autocrud.resource_manager.meta_store.fast_slow import FastSlowMetaStore
            from autocrud.resource_manager.meta_store.postgres import PostgresMetaStore
            from autocrud.resource_manager.meta_store.redis import RedisMetaStore

            # Setup Redis and PostgreSQL connections
            redis_url = "redis://localhost:6379/0"
            pg_dsn = (
                "postgresql://postgres:mysecretpassword@localhost:5432/your_database"
            )

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
                pytest.skip(f"Redis or PostgreSQL not available: {e}")
        else:
            raise ValueError(f"Unsupported store_type: {store_type}")

    def test_search_create_time_timezone(self):
        """Test using IMetaStore.iter_search for created_time filtering."""
        # Search for users created after a specific time
        specific_time = dt.datetime(2023, 1, 1, 4, 0, 0, tzinfo=dt.timezone.utc)

        query = ResourceMetaSearchQuery(
            created_time_start=specific_time,
            created_time_end=specific_time,
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 2 users (Diana and Eve)
        assert len(results) == 1
        names = []
        for meta in results:
            names.append(meta.indexed_data["name"])
        assert sorted(names) == ["Alice"]

    def _create_sample_resource_metas(self, meta_store):
        """Create sample ResourceMeta objects for testing."""
        import uuid

        base_time = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        sample_metas = [
            ResourceMeta(
                current_revision_id="rev_1",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base_time,
                updated_time=base_time,
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Alice",
                    "email": "alice@company.com",
                    "age": 25,
                    "department": "Engineering",
                },
            ),
            ResourceMeta(
                current_revision_id="rev_2",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=1),
                updated_time=base_time + dt.timedelta(minutes=1),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Bob",
                    "email": "bob@company.com",
                    "age": 30,
                    "department": "Marketing",
                },
            ),
            ResourceMeta(
                current_revision_id="rev_3",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=2),
                updated_time=base_time + dt.timedelta(minutes=2),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Charlie",
                    "email": "charlie@external.org",
                    "age": 35,
                    "department": "Engineering",
                },
            ),
            ResourceMeta(
                current_revision_id="rev_4",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=3),
                updated_time=base_time + dt.timedelta(minutes=3),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Diana",
                    "email": "diana@company.com",
                    "age": 28,
                    "department": "Sales",
                },
            ),
            ResourceMeta(
                current_revision_id="rev_5",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=4),
                updated_time=base_time + dt.timedelta(minutes=4),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Eve",
                    "email": "eve@company.com",
                    "age": 32,
                    "department": "Engineering",
                },
            ),
        ]

        # 將樣本數據存儲到 MetaStore 中
        for meta in sample_metas:
            meta_store[meta.resource_id] = meta

        return sample_metas
