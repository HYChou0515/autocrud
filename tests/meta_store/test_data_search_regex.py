import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMeta,
    ResourceMetaSearchQuery,
)

from .common import ALL_META_STORE_TYPES, get_meta_store


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.parametrize(
    "meta_store_type",
    ALL_META_STORE_TYPES,
)
class TestMetaStoreRegexSearch:
    """Test regex search functionality."""

    @pytest.fixture(autouse=True)
    def setup_method(self, meta_store_type, my_tmpdir):
        self.meta_store = get_meta_store(meta_store_type, my_tmpdir)
        self._create_sample_resource_metas(self.meta_store)

    def test_regex_search(self):
        """Test regex search."""
        # Search for emails ending with company.com
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="email",
                    operator=DataSearchOperator.regex,
                    value=r".*@company\.com$",
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query))

        # Should find Alice, Bob, Diana, Eve (4 users)
        # Charlie is @external.org
        assert len(results) == 4
        names = sorted([meta.indexed_data["name"] for meta in results])
        assert names == ["Alice", "Bob", "Diana", "Eve"]

    def test_regex_search_start_with_a(self):
        """Test regex search for names starting with A."""
        query = ResourceMetaSearchQuery(
            data_conditions=[
                DataSearchCondition(
                    field_path="name",
                    operator=DataSearchOperator.regex,
                    value=r"^A.*",
                ),
            ],
        )

        results = list(self.meta_store.iter_search(query))

        # Should find Alice
        assert len(results) == 1
        assert results[0].indexed_data["name"] == "Alice"

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
