import datetime as dt
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from msgspec import UNSET, Struct

from autocrud.resource_manager.core import IndexedValueExtractor
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IndexableField,
    ResourceDataSearchSort,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSortDirection,
    SpecialIndex,
)


class UserRole(Enum):
    ADMIN = "管理員"
    DEVELOPER = "開發者"
    ANALYST = "分析師"


class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class Status(Enum):
    PENDING = auto()  # 1
    ACTIVE = auto()  # 2
    DONE = auto()  # 3


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
        "sql3-s3",  # S3SqliteMetaStore with MinIO
        "memory-pg",
        "redis",
        "redis-pg",  # FastSlowMetaStore with Redis + PostgreSQL
        "postgres",
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

    def test_iter_search_dotted_field(self):
        """Test search using a field with dots in its name."""
        import uuid

        now = dt.datetime.now(ZoneInfo("UTC"))

        # Add a record with a dotted index key
        meta = ResourceMeta(
            resource_id=str(uuid.uuid4()),
            current_revision_id="rev_dot",
            total_revision_count=1,
            created_time=now,
            updated_time=now,
            created_by="test_user",
            updated_by="test_user",
            is_deleted=False,
            indexed_data={"user.name": "DottedUser", "other": "value"},
        )
        self.meta_store[meta.resource_id] = meta

        # Search using the dotted field
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="user.name",
                    operator=DataSearchOperator.equals,
                    value="DottedUser",
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query))
        assert len(results) == 1
        assert results[0].indexed_data["user.name"] == "DottedUser"

    def test_length_transform_on_string_field(self):
        """Test using length() transform on string fields (name field)."""
        from autocrud.query import QB

        # Create condition: name.length() > 6 (should match "Charlie" only, not "Task 1/2/3")
        condition = QB["name"].length() > 6

        query = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find Charlie (7 chars), exclude Alice (5), Bob (3), Diana (5), Eve (3), Task 1/2/3 (6 chars)
        assert len(results) == 1
        assert results[0].indexed_data["name"] == "Charlie"

    def test_length_transform_on_email_field(self):
        """Test using length() transform with different operators."""
        from autocrud.query import QB

        # Find emails with length >= 20
        condition = QB["email"].length() >= 20

        query = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # charlie@external.org = 21 chars
        # alice@company.com = 17 chars
        # Should only find Charlie
        assert len(results) == 1
        assert results[0].indexed_data["email"] == "charlie@external.org"

    def test_length_transform_equals(self):
        """Test using length() with exact equality."""
        from autocrud.query import QB

        # Find names with exactly 3 characters
        condition = QB["name"].length().eq(3)

        query = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Bob (3) and Eve (3)
        assert len(results) == 2
        names = sorted([r.indexed_data["name"] for r in results])
        assert names == ["Bob", "Eve"]

    def test_length_transform_with_list_field(self):
        """Test using length() transform on list/array fields."""
        import uuid

        from autocrud.query import QB

        now = dt.datetime.now(ZoneInfo("UTC"))

        # Add resources with tags (list field)
        metas_with_tags = [
            ResourceMeta(
                resource_id=str(uuid.uuid4()),
                current_revision_id="rev_tags_1",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Product1",
                    "tags": ["python", "fastapi", "autocrud"],
                },
            ),
            ResourceMeta(
                resource_id=str(uuid.uuid4()),
                current_revision_id="rev_tags_2",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Product2",
                    "tags": ["react"],
                },
            ),
            ResourceMeta(
                resource_id=str(uuid.uuid4()),
                current_revision_id="rev_tags_3",
                total_revision_count=1,
                created_time=now,
                updated_time=now,
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Product3",
                    "tags": [],
                },
            ),
        ]

        for meta in metas_with_tags:
            self.meta_store[meta.resource_id] = meta

        # Find resources with more than 1 tag
        condition = QB["tags"].length() > 1

        query = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Should find Product1 (3 tags)
        assert len(results) == 1
        assert results[0].indexed_data["name"] == "Product1"
        assert len(results[0].indexed_data["tags"]) == 3

    def test_length_transform_with_combined_conditions(self):
        """Test length() combined with other conditions."""
        from autocrud.query import QB

        # Find Engineering users with name length > 4
        condition = (QB["department"].eq("Engineering")) & (QB["name"].length() > 4)

        query = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
            limit=10,
            offset=0,
        )

        results = list(self.meta_store.iter_search(query))

        # Engineering: Alice (5), Charlie (7), Eve (3)
        # name.length() > 4: Alice (5), Charlie (7)
        assert len(results) == 2
        names = sorted([r.indexed_data["name"] for r in results])
        assert names == ["Alice", "Charlie"]

    def test_search_with_enum_value(self):
        """Test search with Enum values - verifies Enum to string/int comparison.

        This test verifies that when we index an Enum field, the indexed data stores
        the Enum's .value (string/int), and search queries using the Enum object should
        correctly match against the stored value.

        Uses the existing sample data which includes a 'role' Enum field.
        """

        from autocrud.query import QB

        # Test 1: Search for all DEVELOPER roles using Enum object
        query_developers = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="role",
                    operator=DataSearchOperator.equals,
                    value=UserRole.DEVELOPER,  # Query with Enum object
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_developers))
        assert len(results) == 2, f"Expected 2 developers, got {len(results)}"
        developer_names = sorted([r.indexed_data["name"] for r in results])
        assert developer_names == ["Alice", "Charlie"]

        # Test 2: Combined condition - Engineering developers (department == Engineering AND role == DEVELOPER)
        condition = (QB["department"].eq("Engineering")) & (
            QB["role"].eq(UserRole.DEVELOPER)
        )

        query_eng_devs = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
        )

        results = list(self.meta_store.iter_search(query_eng_devs))
        assert len(results) == 2, (
            f"Expected 2 engineering developers, got {len(results)}"
        )
        eng_dev_names = sorted([r.indexed_data["name"] for r in results])
        assert eng_dev_names == ["Alice", "Charlie"]

        # Test 3: Search for ADMIN role
        query_admins = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="role",
                    operator=DataSearchOperator.equals,
                    value=UserRole.ADMIN,
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_admins))
        assert len(results) == 1
        assert results[0].indexed_data["name"] == "Bob"

        # Test 4: Search for ANALYST role
        query_analysts = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="role",
                    operator=DataSearchOperator.equals,
                    value=UserRole.ANALYST,
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_analysts))
        assert len(results) == 2
        analyst_names = sorted([r.indexed_data["name"] for r in results])
        assert analyst_names == ["Diana", "Eve"]

    def test_search_with_enum_int_values(self):
        """Test search with Enum using integer values (including auto()).

        This test verifies that Enum fields with int values work correctly.
        Covers both explicit int values and auto() generated values.

        Uses the existing sample data which includes Priority and Status Enum fields.
        """
        from autocrud.query import QB

        # Test 1: Search by int Enum (explicit value)
        query_high_priority = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="priority",
                    operator=DataSearchOperator.equals,
                    value=Priority.HIGH,  # Query with Enum object
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_high_priority))
        assert len(results) == 2, f"Expected 2 high priority tasks, got {len(results)}"
        high_priority_names = sorted([r.indexed_data["name"] for r in results])
        assert high_priority_names == ["Task 1", "Task 3"]

        # Test 2: Search by auto() Enum
        query_active = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="status",
                    operator=DataSearchOperator.equals,
                    value=Status.ACTIVE,  # auto() generated value: 2
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_active))
        assert len(results) == 1, f"Expected 1 active task, got {len(results)}"
        assert results[0].indexed_data["name"] == "Task 1"

        # Test 3: Combined condition with int Enums
        condition = (QB["priority"].eq(Priority.HIGH)) & (
            QB["status"].eq(Status.PENDING)
        )

        query_combined = ResourceMetaSearchQuery(
            data_conditions=[condition._condition],
        )

        results = list(self.meta_store.iter_search(query_combined))
        assert len(results) == 1, (
            f"Expected 1 high priority pending task, got {len(results)}"
        )
        assert results[0].indexed_data["name"] == "Task 3"

        # Test 4: Greater than with int Enum values
        query_priority_gt = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="priority",
                    operator=DataSearchOperator.greater_than,
                    value=Priority.LOW,  # priority > 1
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_priority_gt))
        assert (
            len(results) == 2
        )  # Task 1 (HIGH=3) and Task 3 (HIGH=3), not Task 2 (LOW=1)
        names = sorted([r.indexed_data["name"] for r in results])
        assert names == ["Task 1", "Task 3"]

        # Test 5: in_list with int Enum values
        query_in_list = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="status",
                    operator=DataSearchOperator.in_list,
                    value=[Status.PENDING, Status.DONE],  # auto() values: [1, 3]
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query_in_list))
        assert len(results) == 2  # Task 2 (DONE) and Task 3 (PENDING)
        names = sorted([r.indexed_data["name"] for r in results])
        assert names == ["Task 2", "Task 3"]

    def _get_meta_store(self, store_type: str, tmpdir):
        """Get meta store instance."""
        from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
        from autocrud.resource_manager.meta_store.sqlite3 import (
            FileSqliteMetaStore,
            MemorySqliteMetaStore,
            S3SqliteMetaStore,
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
        if store_type == "sql3-s3":
            # Use real S3/MinIO connection
            import uuid

            test_key = f"test-data-search-{uuid.uuid4()}.db"
            try:
                store = S3SqliteMetaStore(
                    bucket="test-autocrud",
                    key=test_key,
                    endpoint_url="http://localhost:9000",
                    access_key_id="minioadmin",
                    secret_access_key="minioadmin",
                    encoding="msgpack",
                    auto_sync=False,
                    enable_locking=False,  # 測試環境禁用鎖定
                )
                # 清理函數會在測試結束後被調用
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
                pytest.skip(f"S3/MinIO not available: {e}")
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
                pytest.skip(f"Redis or PostgreSQL not available: {e}")
        elif store_type == "postgres":
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
                pytest.skip(f"PostgreSQL not available: {e}")
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
                    "role": UserRole.DEVELOPER.value,  # Enum stored as string
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
                    "role": UserRole.ADMIN.value,  # Enum stored as string
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
                    "role": UserRole.DEVELOPER.value,  # Enum stored as string
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
                    "role": UserRole.ANALYST.value,  # Enum stored as string
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
                    "role": UserRole.ANALYST.value,  # Enum stored as string
                },
            ),
            # Task data with int Enum values
            ResourceMeta(
                resource_id=str(uuid.uuid4()),
                current_revision_id="rev_task_1",
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=10),
                updated_time=base_time + dt.timedelta(minutes=10),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Task 1",
                    "priority": Priority.HIGH.value,  # Stored as int: 3
                    "status": Status.ACTIVE.value,  # Stored as int: 2
                },
            ),
            ResourceMeta(
                resource_id=str(uuid.uuid4()),
                current_revision_id="rev_task_2",
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=11),
                updated_time=base_time + dt.timedelta(minutes=11),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Task 2",
                    "priority": Priority.LOW.value,  # Stored as int: 1
                    "status": Status.DONE.value,  # Stored as int: 3
                },
            ),
            ResourceMeta(
                resource_id=str(uuid.uuid4()),
                current_revision_id="rev_task_3",
                total_revision_count=1,
                created_time=base_time + dt.timedelta(minutes=12),
                updated_time=base_time + dt.timedelta(minutes=12),
                created_by="test_user",
                updated_by="test_user",
                is_deleted=False,
                indexed_data={
                    "name": "Task 3",
                    "priority": Priority.HIGH.value,  # Stored as int: 3
                    "status": Status.PENDING.value,  # Stored as int: 1
                },
            ),
        ]

        # 將樣本數據存儲到 MetaStore 中
        for meta in sample_metas:
            meta_store[meta.resource_id] = meta

        return sample_metas


class TestIndexedValueExtractor:
    """測試 IndexedValueExtractor 類的功能"""

    def test_extract_simple_fields(self):
        """測試提取簡單欄位"""

        class User(Struct):
            name: str
            age: int
            email: str

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="age", field_type=int),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        user = User(name="Alice", age=30, email="alice@example.com")
        result = extractor.extract_indexed_values(user)

        assert result == {"name": "Alice", "age": 30}

    def test_extract_nested_fields(self):
        """測試提取嵌套欄位"""

        class Address(Struct):
            city: str
            country: str

        class User(Struct):
            name: str
            address: Address

        indexed_fields = [
            IndexableField(field_path="address.city", field_type=str),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        user = User(name="Bob", address=Address(city="Taipei", country="Taiwan"))
        result = extractor.extract_indexed_values(user)

        assert result == {"address.city": "Taipei"}

    def test_extract_enum_string_values(self):
        """測試 Enum（字符串值）保留原始 Enum 對象（序列化時才轉換）"""

        class User(Struct):
            name: str
            role: UserRole

        indexed_fields = [
            IndexableField(field_path="role", field_type=UserRole),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        user = User(name="Charlie", role=UserRole.DEVELOPER)
        result = extractor.extract_indexed_values(user)

        # 提取階段保留 Enum 對象，序列化時才轉換為 .value
        assert result == {"role": UserRole.DEVELOPER}
        assert isinstance(result["role"], UserRole)
        assert result["role"].value == "開發者"

    def test_extract_enum_int_values(self):
        """測試 Enum（整數值）保留原始 Enum 對象（序列化時才轉換）"""

        class Task(Struct):
            name: str
            priority: Priority

        indexed_fields = [
            IndexableField(field_path="priority", field_type=Priority),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        task = Task(name="Important Task", priority=Priority.HIGH)
        result = extractor.extract_indexed_values(task)

        # 提取階段保留 Enum 對象，序列化時才轉換為 .value
        assert result == {"priority": Priority.HIGH}
        assert isinstance(result["priority"], Priority)
        assert result["priority"].value == 3

    def test_extract_enum_auto_values(self):
        """測試 Enum（auto() 生成的值）保留原始 Enum 對象（序列化時才轉換）"""

        class Task(Struct):
            name: str
            status: Status

        indexed_fields = [
            IndexableField(field_path="status", field_type=Status),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        task = Task(name="Active Task", status=Status.ACTIVE)
        result = extractor.extract_indexed_values(task)

        # 提取階段保留 Enum 對象，序列化時才轉換為 auto() 生成的值
        assert result == {"status": Status.ACTIVE}
        assert isinstance(result["status"], Status)
        assert result["status"].value == 2

    def test_extract_multiple_fields_with_enum(self):
        """測試同時提取多個欄位，包含 Enum（保留原始對象）"""

        class User(Struct):
            name: str
            age: int
            role: UserRole

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="age", field_type=int),
            IndexableField(field_path="role", field_type=UserRole),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        user = User(name="David", age=25, role=UserRole.ANALYST)
        result = extractor.extract_indexed_values(user)

        assert result == {"name": "David", "age": 25, "role": UserRole.ANALYST}
        assert result["role"].value == "分析師"

    def test_extract_msgspec_tag(self):
        """測試提取 msgspec tag（用於 Union 類型識別）"""

        class Dog(Struct, tag="dog"):
            name: str

        class Cat(Struct, tag="cat"):
            name: str

        indexed_fields = [
            IndexableField(field_path="type", field_type=SpecialIndex.msgspec_tag),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        dog = Dog(name="Buddy")
        result = extractor.extract_indexed_values(dog)

        assert result == {"type": "dog"}

    def test_extract_nonexistent_field(self):
        """測試提取不存在的欄位（會返回 None）"""

        class User(Struct):
            name: str

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="age", field_type=int),  # 不存在
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        user = User(name="Eve")
        result = extractor.extract_indexed_values(user)

        # 不存在的欄位會被存為 None
        assert result == {"name": "Eve", "age": None}

    def test_extract_with_unset_value(self):
        """測試欄位值為 UNSET 的情況"""

        class User(Struct):
            name: str
            email: str | None = None

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="email", field_type=str | None),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        user = User(name="Frank", email=None)
        result = extractor.extract_indexed_values(user)

        # None 值應該被提取
        assert result == {"name": "Frank", "email": None}

    def test_extract_datetime_field(self):
        """測試提取 datetime 類型欄位"""

        class Event(Struct):
            name: str
            created_at: dt.datetime
            updated_at: dt.datetime | None = None

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="created_at", field_type=dt.datetime),
            IndexableField(field_path="updated_at", field_type=dt.datetime | None),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        created_time = dt.datetime(2023, 1, 15, 10, 30, 0, tzinfo=dt.timezone.utc)
        updated_time = dt.datetime(2023, 1, 16, 12, 0, 0, tzinfo=dt.timezone.utc)

        event = Event(
            name="Conference", created_at=created_time, updated_at=updated_time
        )
        result = extractor.extract_indexed_values(event)

        assert result == {
            "name": "Conference",
            "created_at": created_time,
            "updated_at": updated_time,
        }
        assert isinstance(result["created_at"], dt.datetime)
        assert isinstance(result["updated_at"], dt.datetime)

    def test_extract_numeric_fields(self):
        """測試提取數值類型欄位（int, float）"""

        class Product(Struct):
            name: str
            price: float
            quantity: int
            discount_rate: float | None = None

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="price", field_type=float),
            IndexableField(field_path="quantity", field_type=int),
            IndexableField(field_path="discount_rate", field_type=float | None),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        product = Product(name="Laptop", price=999.99, quantity=10, discount_rate=0.15)
        result = extractor.extract_indexed_values(product)

        assert result == {
            "name": "Laptop",
            "price": 999.99,
            "quantity": 10,
            "discount_rate": 0.15,
        }
        assert isinstance(result["price"], float)
        assert isinstance(result["quantity"], int)
        assert isinstance(result["discount_rate"], float)

    def test_extract_boolean_field(self):
        """測試提取布林類型欄位"""

        class Setting(Struct):
            name: str
            enabled: bool
            is_public: bool

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="enabled", field_type=bool),
            IndexableField(field_path="is_public", field_type=bool),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        setting = Setting(name="Feature Flag", enabled=True, is_public=False)
        result = extractor.extract_indexed_values(setting)

        assert result == {"name": "Feature Flag", "enabled": True, "is_public": False}
        assert isinstance(result["enabled"], bool)
        assert isinstance(result["is_public"], bool)

    def test_extract_list_field(self):
        """測試提取列表類型欄位"""

        class Project(Struct):
            name: str
            tags: list[str]
            contributors: list[str]

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="tags", field_type=list[str]),
            IndexableField(field_path="contributors", field_type=list[str]),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        project = Project(
            name="AutoCRUD",
            tags=["python", "fastapi", "crud"],
            contributors=["Alice", "Bob"],
        )
        result = extractor.extract_indexed_values(project)

        assert result == {
            "name": "AutoCRUD",
            "tags": ["python", "fastapi", "crud"],
            "contributors": ["Alice", "Bob"],
        }
        assert isinstance(result["tags"], list)
        assert len(result["tags"]) == 3

    def test_extract_dict_field(self):
        """測試提取字典類型欄位"""

        class Config(Struct):
            name: str
            settings: dict[str, str | int]

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="settings", field_type=dict),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        config = Config(
            name="Database Config", settings={"host": "localhost", "port": 5432}
        )
        result = extractor.extract_indexed_values(config)

        assert result == {
            "name": "Database Config",
            "settings": {"host": "localhost", "port": 5432},
        }
        assert isinstance(result["settings"], dict)
        assert result["settings"]["port"] == 5432

    def test_extract_mixed_types(self):
        """測試同時提取多種不同類型的欄位"""

        class ComplexRecord(Struct):
            id: int
            name: str
            price: float
            active: bool
            tags: list[str]
            created_at: dt.datetime
            role: UserRole
            priority: Priority

        indexed_fields = [
            IndexableField(field_path="id", field_type=int),
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="price", field_type=float),
            IndexableField(field_path="active", field_type=bool),
            IndexableField(field_path="tags", field_type=list[str]),
            IndexableField(field_path="created_at", field_type=dt.datetime),
            IndexableField(field_path="role", field_type=UserRole),
            IndexableField(field_path="priority", field_type=Priority),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        created_time = dt.datetime(2023, 6, 1, 14, 30, 0, tzinfo=dt.timezone.utc)
        record = ComplexRecord(
            id=123,
            name="Complex Item",
            price=49.99,
            active=True,
            tags=["urgent", "review"],
            created_at=created_time,
            role=UserRole.ADMIN,
            priority=Priority.HIGH,
        )
        result = extractor.extract_indexed_values(record)

        assert result == {
            "id": 123,
            "name": "Complex Item",
            "price": 49.99,
            "active": True,
            "tags": ["urgent", "review"],
            "created_at": created_time,
            "role": UserRole.ADMIN,  # 保留 Enum 對象
            "priority": Priority.HIGH,  # 保留 Enum 對象
        }

        # 驗證類型
        assert isinstance(result["id"], int)
        assert isinstance(result["name"], str)
        assert isinstance(result["price"], float)
        assert isinstance(result["active"], bool)
        assert isinstance(result["tags"], list)
        assert isinstance(result["created_at"], dt.datetime)
        assert isinstance(result["role"], UserRole)  # Enum 保留為對象
        assert isinstance(result["priority"], Priority)  # Enum 保留為對象
        assert result["role"].value == "管理員"
        assert result["priority"].value == 3

    def test_extract_deeply_nested_fields(self):
        """測試提取深度嵌套的欄位"""

        class Location(Struct):
            lat: float
            lng: float

        class Address(Struct):
            street: str
            city: str
            location: Location

        class Company(Struct):
            name: str
            address: Address

        indexed_fields = [
            IndexableField(field_path="name", field_type=str),
            IndexableField(field_path="address.city", field_type=str),
            IndexableField(field_path="address.location.lat", field_type=float),
            IndexableField(field_path="address.location.lng", field_type=float),
        ]
        extractor = IndexedValueExtractor(indexed_fields)

        company = Company(
            name="TechCorp",
            address=Address(
                street="123 Main St",
                city="San Francisco",
                location=Location(lat=37.7749, lng=-122.4194),
            ),
        )
        result = extractor.extract_indexed_values(company)

        assert result == {
            "name": "TechCorp",
            "address.city": "San Francisco",
            "address.location.lat": 37.7749,
            "address.location.lng": -122.4194,
        }
        assert isinstance(result["address.location.lat"], float)
        assert isinstance(result["address.location.lng"], float)
