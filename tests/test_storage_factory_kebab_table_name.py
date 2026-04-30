"""
Tests for PostgreSQL storage factories always using snake_case table names.

When model_naming is "kebab", model names like "game-event" would produce
invalid PostgreSQL table names (hyphens are not allowed in unquoted identifiers).
All PostgreSQL storage factories must convert model names to snake_case for table naming.
"""

import datetime as dt
from pathlib import Path
from unittest.mock import patch

import pytest
from faker import Faker
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.storage_factory import (
    PostgresDiskStorageFactory,
    PostgreSQLS3StorageFactory,
    PostgresStorageFactory,
    _pg_safe_name,
)
from tests.meta_store.common import ALL_META_STORE_TYPES, get_meta_store

faker = Faker()

# (model_name_input, expected_snake_name)
NAMING_CASES = [
    ("game-event", "game_event"),
    ("game_event", "game_event"),
    ("GameEvent", "game_event"),
    ("gameEvent", "game_event"),
    ("character", "character"),
    ("my-long-resource-name", "my_long_resource_name"),
    ("MyLongResourceName", "my_long_resource_name"),
]

FACTORY_TYPES = ["postgres", "postgres_s3", "postgres_disk"]


# ---------------------------------------------------------------------------
# Unit test: _pg_safe_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("model_name, expected_snake", NAMING_CASES)
def test_pg_safe_name(model_name, expected_snake):
    assert _pg_safe_name(model_name) == expected_snake


# ---------------------------------------------------------------------------
# Unit test: factory build() produces correct table names (mock-based)
# ---------------------------------------------------------------------------


def _build_with_mock(factory_type: str, model_name: str, table_prefix: str = ""):
    """Build a factory of the given type with mocked backends and return the mock_pg."""
    if factory_type == "postgres":
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.PostgresResourceStore"
            ) as mock_res,
        ):
            factory = PostgresStorageFactory(
                connection_string="postgresql://localhost/db",
                table_prefix=table_prefix,
            )
            factory.build(model_name)
            return mock_pg, mock_res

    if factory_type == "postgres_s3":
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.S3ResourceStore"
            ) as mock_res,
        ):
            factory = PostgreSQLS3StorageFactory(
                connection_string="postgresql://localhost/db",
                s3_bucket="bucket",
                table_prefix=table_prefix,
            )
            factory.build(model_name)
            return mock_pg, mock_res

    if factory_type == "postgres_disk":
        with (
            patch(
                "autocrud.resource_manager.storage_factory.PostgresMetaStore"
            ) as mock_pg,
            patch(
                "autocrud.resource_manager.storage_factory.DiskResourceStore"
            ) as mock_res,
        ):
            factory = PostgresDiskStorageFactory(
                connection_string="postgresql://localhost/db",
                rootdir="/tmp/test",
                table_prefix=table_prefix,
            )
            factory.build(model_name)
            return mock_pg, mock_res

    raise ValueError(f"Unknown factory type: {factory_type}")


@pytest.mark.parametrize("factory_type", FACTORY_TYPES)
@pytest.mark.parametrize("model_name, expected_snake", NAMING_CASES)
class TestPgSafeTableNaming:
    """All PostgreSQL storage factories must produce snake_case table names."""

    def test_meta_table_name_without_prefix(
        self, factory_type, model_name, expected_snake
    ):
        mock_pg, _ = _build_with_mock(factory_type, model_name, table_prefix="")
        pg_kwargs = mock_pg.call_args[1]
        assert pg_kwargs["table_name"] == f"{expected_snake}_meta"

    def test_meta_table_name_with_prefix(
        self, factory_type, model_name, expected_snake
    ):
        mock_pg, _ = _build_with_mock(factory_type, model_name, table_prefix="app_")
        pg_kwargs = mock_pg.call_args[1]
        assert pg_kwargs["table_name"] == f"app_{expected_snake}_meta"

    def test_resource_table_prefix(self, factory_type, model_name, expected_snake):
        """PostgresStorageFactory resource store should also use snake_case prefix."""
        if factory_type != "postgres":
            pytest.skip("resource table_prefix only applies to PostgresStorageFactory")
        mock_pg, mock_res = _build_with_mock(factory_type, model_name, table_prefix="")
        res_kwargs = mock_res.call_args[1]
        assert res_kwargs["table_prefix"] == f"{expected_snake}_"


# ---------------------------------------------------------------------------
# Integration test: CRUD works with safe-named stores across all meta stores
# ---------------------------------------------------------------------------


class SimpleData(Struct):
    name: str
    value: int


@pytest.fixture
def my_tmpdir():
    """Fixture to provide a temporary directory for testing."""
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.flaky(retries=3, delay=1)
@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
@pytest.mark.parametrize(
    "model_name",
    ["game-event", "GameEvent", "game_event", "gameEvent"],
)
class TestSafeNamingIntegration:
    """Verify ResourceManager CRUD works with _pg_safe_name-derived names
    across all meta store backends."""

    @pytest.fixture(autouse=True)
    def setup(self, meta_store_type: str, model_name: str, my_tmpdir: Path):
        meta_store = get_meta_store(meta_store_type, tmpdir=my_tmpdir)
        resource_store = MemoryResourceStore(encoding="msgpack")  # ty:ignore[invalid-argument-type]
        storage = SimpleStorage(
            meta_store=meta_store,
            resource_store=resource_store,
        )
        self.mgr = ResourceManager(SimpleData, storage=storage)
        yield

    def test_create_and_get(self, meta_store_type, model_name):
        """Create a resource and read it back — verifies nothing blows up
        for any meta store with any naming convention."""
        data = SimpleData(name=f"test-{model_name}", value=42)
        user, now = faker.user_name(), dt.datetime(2025, 1, 1, 12, 0, 0)
        with self.mgr.meta_provide(user, now):
            info = self.mgr.create(data)
        got = self.mgr.get(info.resource_id)
        assert got.data == data
        assert got.info.created_by == user

    def test_search(self, meta_store_type, model_name):
        """Search after create — verifies meta store indexing works."""
        from autocrud.query_types import ResourceMetaSearchQuery

        data = SimpleData(name=f"search-{model_name}", value=99)
        user, now = faker.user_name(), dt.datetime(2025, 6, 1)
        with self.mgr.meta_provide(user, now):
            info = self.mgr.create(data)

        query = ResourceMetaSearchQuery(created_bys=[user])
        with self.mgr.meta_provide(user, now):
            results = self.mgr.search_resources(query)

        result_ids = [r.resource_id for r in results]
        assert info.resource_id in result_ids
