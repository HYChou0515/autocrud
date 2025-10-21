import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from msgspec import UNSET

from autocrud.resource_manager.meta_store.simple import (
    MemoryContentMetaStore,
    MemoryMetaStore,
)
from autocrud.types import (
    ContentMeta,
    ContentMetaSearchQuery,
    ContentMetaSearchSort,
    ContentMetaSortKey,
    ResourceMetaSortDirection,
    SortDirection,
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


@pytest.mark.parametrize(
    "meta_store_type",
    [
        "memory",
    ],
)
class TestContentMetaStore:
    @pytest.fixture(autouse=True)
    def setup_method(self, meta_store_type, my_tmpdir):
        self.meta_store = self._get_meta_store(meta_store_type, my_tmpdir)
        sample_metas = self._create_sample_resource_metas(self.meta_store)

    def _get_meta_store(self, store_type: str, tmpdir):
        """Get meta store instance."""

        if store_type == "memory":
            return MemoryContentMetaStore(encoding="msgpack")
        raise ValueError(f"Unsupported store_type: {store_type}")

    def _create_sample_resource_metas(self, meta_store):
        """Create sample ResourceMeta objects for testing."""
        import uuid

        base_time = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        sample_metas = [
            ContentMeta(
                resource_id=str(uuid.uuid4()),
                created_time=base_time,
                created_by="user1",
                accessed_time=base_time + dt.timedelta(minutes=10),
                accessed_by="user1",
                mime="image/jpeg",
                size=1024000,  # 1MB
                hash="hash1",
            ),
            ContentMeta(
                resource_id=str(uuid.uuid4()),
                created_time=base_time + dt.timedelta(minutes=1),
                created_by="user2",
                accessed_time=base_time + dt.timedelta(minutes=15),
                accessed_by="user2",
                mime="application/pdf",
                size=2048000,  # 2MB
                hash="hash2",
            ),
            ContentMeta(
                resource_id=str(uuid.uuid4()),
                created_time=base_time + dt.timedelta(minutes=2),
                created_by="user1",
                accessed_time=base_time + dt.timedelta(minutes=20),
                accessed_by="user3",
                mime="text/plain",
                size=512000,  # 512KB
                hash="hash3",
            ),
            ContentMeta(
                resource_id=str(uuid.uuid4()),
                created_time=base_time + dt.timedelta(minutes=3),
                created_by="user3",
                accessed_time=base_time + dt.timedelta(minutes=25),
                accessed_by="user1",
                mime="video/mp4",
                size=10240000,  # 10MB
                hash="hash4",
            ),
            ContentMeta(
                resource_id=str(uuid.uuid4()),
                created_time=base_time + dt.timedelta(minutes=4),
                created_by="user2",
                accessed_time=base_time + dt.timedelta(minutes=30),
                accessed_by="user2",
                mime="application/json",
                size=256000,  # 256KB
                hash="hash5",
            ),
        ]

        # 將樣本數據存儲到 MetaStore 中
        for meta in sample_metas:
            meta_store[meta.resource_id] = meta

        return sample_metas

    def test_search_by_mime_type(self):
        """Test searching ContentMeta by MIME type."""
        query = ContentMetaSearchQuery(
            mimes=["image/jpeg", "application/pdf"],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 2 files (JPEG and PDF)
        assert len(results) == 2
        mimes = [meta.mime for meta in results]
        assert "image/jpeg" in mimes
        assert "application/pdf" in mimes

    def test_search_by_size_range(self):
        """Test searching ContentMeta by file size range."""
        query = ContentMetaSearchQuery(
            min_size=1000000,  # 1MB
            max_size=5000000,  # 5MB
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 2 files (JPEG: 1MB, PDF: 2MB)
        assert len(results) == 2
        for meta in results:
            assert 1000000 <= meta.size <= 5000000

    def test_search_by_created_by_user(self):
        """Test searching ContentMeta by creator."""
        query = ContentMetaSearchQuery(
            created_bys=["user1", "user2"],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 4 files created by user1 or user2
        assert len(results) == 4
        creators = {meta.created_by for meta in results}
        assert creators == {"user1", "user2"}

    def test_search_by_accessed_by_user(self):
        """Test searching ContentMeta by accessor."""
        query = ContentMetaSearchQuery(
            accessed_bys=["user3"],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 1 file accessed by user3
        assert len(results) == 1
        assert results[0].accessed_by == "user3"
        assert results[0].mime == "text/plain"

    def test_search_by_time_range(self):
        """Test searching ContentMeta by time ranges."""
        base_time = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        query = ContentMetaSearchQuery(
            created_time_start=base_time + dt.timedelta(minutes=1),
            created_time_end=base_time + dt.timedelta(minutes=3),
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 2 files created between minute 1 and 3
        assert len(results) == 3
        for meta in results:
            assert (
                base_time + dt.timedelta(minutes=1)
                <= meta.created_time
                <= base_time + dt.timedelta(minutes=3)
            )

    def test_search_with_sorting_by_size(self):
        """Test searching ContentMeta with sorting by file size."""
        query = ContentMetaSearchQuery(
            sorts=[
                ContentMetaSearchSort(
                    key=ContentMetaSortKey.size,
                    direction=SortDirection.ascending,
                )
            ],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should return all files sorted by size (ascending)
        assert len(results) == 5
        sizes = [meta.size for meta in results]
        assert sizes == sorted(sizes)
        assert sizes == [256000, 512000, 1024000, 2048000, 10240000]

    def test_search_with_sorting_by_created_time(self):
        """Test searching ContentMeta with sorting by created time."""
        query = ContentMetaSearchQuery(
            sorts=[
                ContentMetaSearchSort(
                    key=ContentMetaSortKey.created_time,
                    direction=SortDirection.descending,
                )
            ],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should return all files sorted by created_time (descending)
        assert len(results) == 5
        created_times = [meta.created_time for meta in results]
        assert created_times == sorted(created_times, reverse=True)

    def test_search_with_combined_filters(self):
        """Test searching ContentMeta with multiple combined filters."""
        base_time = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=ZoneInfo("Asia/Taipei"))

        query = ContentMetaSearchQuery(
            created_bys=["user1", "user2"],
            min_size=500000,
            max_size=2500000,
            created_time_start=base_time,
            created_time_end=base_time + dt.timedelta(minutes=2),
            sorts=[
                ContentMetaSearchSort(
                    key=ContentMetaSortKey.size,
                    direction=SortDirection.ascending,
                )
            ],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find 3 files that match all criteria
        assert len(results) == 3
        for meta in results:
            assert meta.created_by in ["user1", "user2", "user3"]
            assert 500000 <= meta.size <= 2500000
            assert base_time <= meta.created_time <= base_time + dt.timedelta(minutes=2)

        sizes = [meta.size for meta in results]
        assert sizes == sorted(sizes)

    def test_search_with_pagination(self):
        """Test searching ContentMeta with pagination."""
        query1 = ContentMetaSearchQuery(
            sorts=[
                ContentMetaSearchSort(
                    key=ContentMetaSortKey.size,
                    direction=SortDirection.ascending,
                )
            ],
            limit=2,
            offset=0,
        )

        results1 = list(self.meta_store.iter_search(query1))
        assert len(results1) == 2

        query2 = ContentMetaSearchQuery(
            sorts=[
                ContentMetaSearchSort(
                    key=ContentMetaSortKey.size,
                    direction=SortDirection.ascending,
                )
            ],
            limit=2,
            offset=2,
        )

        results2 = list(self.meta_store.iter_search(query2))
        assert len(results2) == 2

        result1_ids = {meta.resource_id for meta in results1}
        result2_ids = {meta.resource_id for meta in results2}
        assert result1_ids.isdisjoint(result2_ids)

        all_results = results1 + results2
        sizes = [meta.size for meta in all_results]
        assert sizes == sorted(sizes)
