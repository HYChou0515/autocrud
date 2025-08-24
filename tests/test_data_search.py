import datetime as dt
from dataclasses import dataclass
import pytest
from autocrud.resource_manager.basic import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
    ResourceMeta,
)
from msgspec import UNSET
from pathlib import Path


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


class TestMetaStoreIterSearch:
    """Test IMetaStore.iter_search method with different storage types."""

    @pytest.mark.parametrize(
        "meta_store_type",
        [
            "memory",
            "sql3-mem",  # SQLite 測試，看是否支持 data_conditions 過濾
        ],
    )
    def test_iter_search_department_filter(self, meta_store_type, my_tmpdir):
        """Test using IMetaStore.iter_search directly for department filtering."""
        meta_store = self._get_meta_store(meta_store_type, my_tmpdir)
        sample_metas = self._create_sample_resource_metas(meta_store)

        # Search for Engineering department users
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="department",
                    operator=DataSearchOperator.equals,
                    value="Engineering",
                )
            ],
            limit=10,
            offset=0,
        )

        # 直接使用 MetaStore 的 iter_search
        results = list(meta_store.iter_search(query))

        # Memory MetaStore 支持 data_conditions 過濾，SQLite 目前不支持
        if meta_store_type == "memory":
            # Should find 3 Engineering users (Alice, Charlie, Eve)
            assert len(results) == 3
            engineering_names = set()
            for meta in results:
                engineering_names.add(meta.indexed_data["name"])
                # Verify indexed data is populated
                assert meta.indexed_data is not UNSET
                assert meta.indexed_data["department"] == "Engineering"
            assert engineering_names == {"Alice", "Charlie", "Eve"}
        elif meta_store_type == "sql3-mem":
            # SQLite 目前不支持 data_conditions 過濾，會返回所有數據
            assert len(results) == 5  # 返回所有用戶
            print(
                f"SQLite MetaStore 不支持 data_conditions 過濾，返回了 {len(results)} 個結果"
            )

    @pytest.mark.parametrize(
        "meta_store_type",
        [
            "memory",
            "sql3-mem",
        ],
    )
    def test_iter_search_age_range(self, meta_store_type, my_tmpdir):
        """Test using IMetaStore.iter_search for age range filtering."""
        meta_store = self._get_meta_store(meta_store_type, my_tmpdir)
        sample_metas = self._create_sample_resource_metas(meta_store)

        # Search for users aged 30 or older
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="age",
                    operator=DataSearchOperator.greater_than_or_equal,
                    value=30,
                )
            ],
            limit=10,
            offset=0,
        )

        results = list(meta_store.iter_search(query))

        if meta_store_type == "memory":
            # Should find 3 users (Bob: 30, Charlie: 35, Eve: 32)
            assert len(results) == 3
            ages = []
            for meta in results:
                ages.append(meta.indexed_data["age"])
                assert meta.indexed_data["age"] >= 30
            assert sorted(ages) == [30, 32, 35]
        elif meta_store_type == "sql3-mem":
            # SQLite 不支持過濾，返回所有數據
            assert len(results) == 5

    @pytest.mark.parametrize(
        "meta_store_type",
        [
            "memory",
            "sql3-mem",
        ],
    )
    def test_iter_search_combined_conditions(self, meta_store_type, my_tmpdir):
        """Test using IMetaStore.iter_search with multiple combined conditions."""
        meta_store = self._get_meta_store(meta_store_type, my_tmpdir)
        sample_metas = self._create_sample_resource_metas(meta_store)

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

        results = list(meta_store.iter_search(query))

        if meta_store_type == "memory":
            # Should find 2 users (Alice: 25, Eve: 32) - Charlie is 35 so excluded
            assert len(results) == 2
            engineering_under_35 = set()
            for meta in results:
                engineering_under_35.add(meta.indexed_data["name"])
                assert meta.indexed_data["department"] == "Engineering"
                assert meta.indexed_data["age"] < 35
            assert engineering_under_35 == {"Alice", "Eve"}
        elif meta_store_type == "sql3-mem":
            # SQLite 不支持過濾，返回所有數據
            assert len(results) == 5

    def _get_meta_store(self, store_type: str, tmpdir):
        """Get meta store instance."""
        from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
        from autocrud.resource_manager.meta_store.sqlite3 import MemorySqliteMetaStore

        if store_type == "memory":
            return MemoryMetaStore(encoding="msgpack")
        elif store_type == "sql3-mem":
            return MemorySqliteMetaStore(encoding="msgpack")
        else:
            raise ValueError(f"Unsupported store_type: {store_type}")

    def _create_sample_resource_metas(self, meta_store):
        """Create sample ResourceMeta objects for testing."""
        import uuid

        base_time = dt.datetime(2023, 1, 1, 12, 0, 0)

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


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)
