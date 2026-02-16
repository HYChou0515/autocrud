"""Integration tests for Schema with ResourceManager and AutoCRUD.add_model."""

from __future__ import annotations

import datetime as dt
import io
import warnings
from typing import IO
from unittest.mock import MagicMock

import msgspec
import pytest
from msgspec import Struct

from autocrud import Schema
from autocrud.resource_manager.core import ResourceManager
from autocrud.types import (
    IMigration,
    IndexableField,
    ResourceMeta,
    RevisionInfo,
    RevisionStatus,
    ValidationError,
)

# =====================================================================
# Test models
# =====================================================================


class ItemV1(Struct):
    name: str
    price: int


class ItemV2(Struct):
    name: str
    price: int
    currency: str


class ItemV3(Struct):
    name: str
    price: int
    currency: str
    discount: float


# =====================================================================
# Migration functions
# =====================================================================


def migrate_v1_to_v2(data: IO[bytes]) -> ItemV2:
    obj = msgspec.json.decode(data.read(), type=ItemV1)
    return ItemV2(name=obj.name, price=obj.price, currency="USD")


def migrate_v2_to_v3(data: IO[bytes]) -> ItemV3:
    obj = msgspec.json.decode(data.read(), type=ItemV2)
    return ItemV3(name=obj.name, price=obj.price, currency=obj.currency, discount=0.0)


def migrate_v1_to_v3_direct(data: IO[bytes]) -> ItemV3:
    obj = msgspec.json.decode(data.read(), type=ItemV1)
    return ItemV3(name=obj.name, price=obj.price, currency="TWD", discount=10.0)


# =====================================================================
# Integration: Schema + ResourceManager
# =====================================================================


class TestSchemaResourceManagerIntegration:
    """Test Schema integrated with ResourceManager."""

    @pytest.fixture
    def mock_storage(self) -> MagicMock:
        return MagicMock()

    def test_rm_with_schema_single_step(self, mock_storage: MagicMock):
        """RM created with migration=Schema, single step migration."""
        schema = Schema(ItemV2, "v2").step("v1", migrate_v1_to_v2)
        rm = ResourceManager(
            resource_type=ItemV2,
            storage=mock_storage,
            migration=schema,
            indexed_fields=[IndexableField("name")],
        )

        assert rm._schema_version == "v2"
        assert rm._migration is not None

    def test_rm_with_schema_chain(self, mock_storage: MagicMock):
        """RM created with migration=Schema, chain migration."""
        schema = (
            Schema(ItemV3, "v3")
            .step("v1", migrate_v1_to_v2)
            .step("v2", migrate_v2_to_v3)
        )
        rm = ResourceManager(
            resource_type=ItemV3,
            storage=mock_storage,
            migration=schema,
        )
        assert rm._schema_version == "v3"

    def test_rm_with_schema_validator(self, mock_storage: MagicMock):
        """Schema validator is used by RM."""

        def check_price(data):
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        schema = Schema(ItemV1, "v1", validator=check_price)
        rm = ResourceManager(
            resource_type=ItemV1,
            storage=mock_storage,
            migration=schema,
        )
        # Validator should be set
        assert rm._validator is not None

        # Good data
        rm._run_validator(ItemV1(name="ok", price=10))

        # Bad data
        with pytest.raises(ValidationError, match="non-negative"):
            rm._run_validator(ItemV1(name="bad", price=-5))

    def test_rm_with_legacy_migration_backward_compat(self, mock_storage: MagicMock):
        """Existing migration= parameter still works (wrapped in Schema)."""

        class LegacyMig(IMigration[ItemV2]):
            @property
            def schema_version(self) -> str:
                return "v2"

            def migrate(self, data: IO[bytes], sv: str | None) -> ItemV2:
                obj = msgspec.json.decode(data.read(), type=ItemV1)
                return ItemV2(name=obj.name, price=obj.price, currency="EUR")

        rm = ResourceManager(
            resource_type=ItemV2,
            storage=mock_storage,
            migration=LegacyMig(),
        )
        assert rm._schema_version == "v2"
        assert rm._schema is not None  # wrapped in Schema

    def test_rm_migrate_with_schema(self, mock_storage: MagicMock):
        """Full migration flow using Schema with ResourceManager.migrate()."""
        schema = Schema(ItemV2, "v2").step("v1", migrate_v1_to_v2)
        rm = ResourceManager(
            resource_type=ItemV2,
            storage=mock_storage,
            migration=schema,
            indexed_fields=[IndexableField("name"), IndexableField("currency")],
        )

        # Set up mock
        legacy_data = ItemV1(name="widget", price=100)
        revision_info = RevisionInfo(
            uid="uid-1",
            resource_id="item:1",
            revision_id="item:1:1",
            schema_version="v1",
            data_hash="hash1",
            status=RevisionStatus.stable,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test",
            updated_by="test",
        )
        meta = ResourceMeta(
            current_revision_id="item:1:1",
            resource_id="item:1",
            schema_version="v1",
            total_revision_count=1,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test",
            updated_by="test",
        )
        meta.is_deleted = False

        mock_storage.exists.return_value = True
        mock_storage.get_meta.return_value = meta
        mock_storage.get_resource_revision_info.return_value = revision_info
        mock_storage.get_data_bytes.return_value.__enter__.return_value = io.BytesIO(
            msgspec.json.encode(legacy_data)
        )

        result = rm.migrate("item:1")

        # Verify migration happened
        mock_storage.save_meta.assert_called_once()
        mock_storage.save_revision.assert_called_once()

        saved_info = mock_storage.save_revision.call_args[0][0]
        assert saved_info.schema_version == "v2"

        saved_data_io = mock_storage.save_revision.call_args[0][1]
        saved_data_io.seek(0)
        saved_data = msgspec.json.decode(saved_data_io.read(), type=ItemV2)
        assert saved_data.currency == "USD"
        assert saved_data.name == "widget"

        # Verify meta updated
        assert result.schema_version == "v2"
        assert result.indexed_data == {"name": "widget", "currency": "USD"}

    def test_rm_no_schema_no_migration(self, mock_storage: MagicMock):
        """RM without schema or migration has no migration capability."""
        rm = ResourceManager(
            resource_type=ItemV1,
            storage=mock_storage,
        )
        assert rm._schema is None
        assert rm._migration is None
        assert rm._schema_version is None

    def test_rm_reindex_only_schema(self, mock_storage: MagicMock):
        """Schema with version but no steps = reindex only."""
        schema = Schema(ItemV2, "v2")
        rm = ResourceManager(
            resource_type=ItemV2,
            storage=mock_storage,
            migration=schema,
        )
        assert rm._schema_version == "v2"
        # No migration steps, but version is set
        assert not schema.has_migration
        # Schema is still stored (for version info), but has no migration steps
        assert rm._schema is not None


# =====================================================================
# Integration: Schema + add_model
# =====================================================================


class TestSchemaAddModelIntegration:
    """Test Schema integrated with AutoCRUD.add_model()."""

    @pytest.fixture
    def app(self):
        from autocrud.crud.core import AutoCRUD

        return AutoCRUD()

    def test_add_model_with_schema_as_first_arg(self, app):
        """add_model with Schema as first argument."""
        schema = Schema(ItemV2, "v2").step("v1", migrate_v1_to_v2)
        app.add_model(schema)
        rm = app.resource_managers["item-v2"]
        assert rm._schema_version == "v2"

    def test_add_model_with_migration_schema(self, app):
        """add_model with migration=Schema."""
        schema = Schema(ItemV2, "v2").step("v1", migrate_v1_to_v2)
        app.add_model(ItemV2, migration=schema)
        rm = app.resource_managers["item-v2"]
        assert rm._schema_version == "v2"

    def test_add_model_legacy_migration_warns(self, app):
        """add_model with migration=IMigration triggers DeprecationWarning."""

        class LegacyMig(IMigration[ItemV2]):
            @property
            def schema_version(self) -> str:
                return "v2"

            def migrate(self, data, sv):
                pass

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app.add_model(ItemV2, migration=LegacyMig())
            assert len(w) == 1
            assert issubclass(w[0].category, DeprecationWarning)
            assert "IMigration" in str(w[0].message)

        rm = app.resource_managers["item-v2"]
        assert rm._schema_version == "v2"

    def test_add_model_schema_with_validator(self, app):
        """add_model with Schema that has a validator."""

        def check(data):
            if data.price < 0:
                raise ValueError("bad")

        schema = Schema(ItemV1, "v1", validator=check)
        app.add_model(schema)
        rm = app.resource_managers["item-v1"]
        assert rm._validator is not None

    def test_add_model_schema_first_arg_and_migration_raises(self, app):
        """Cannot specify migration= when Schema is the first argument."""
        schema = Schema(ItemV2, "v2")
        with pytest.raises(ValueError, match="Cannot specify 'migration'"):
            app.add_model(schema, migration=Schema(ItemV2, "v2"))

    def test_add_model_schema_first_arg_and_validator_raises(self, app):
        """Cannot specify validator= when Schema is the first argument."""

        def check(data):
            pass

        schema = Schema(ItemV2, "v2", validator=check)
        with pytest.raises(ValueError, match="Cannot specify 'validator'"):
            app.add_model(schema, validator=lambda d: None)

    def test_add_model_type_only_no_warning(self, app):
        """add_model(type) without migration/schema works without warning."""
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            app.add_model(ItemV1)
            # No deprecation warning
            dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
            assert len(dep_warnings) == 0

        rm = app.resource_managers["item-v1"]
        assert rm._schema is None

    def test_add_model_type_with_validator(self, app):
        """add_model(type, validator=fn) works."""

        def check(data):
            if data.price < 0:
                raise ValueError("bad")

        app.add_model(ItemV1, validator=check)
        rm = app.resource_managers["item-v1"]
        assert rm._validator is not None

    def test_add_model_pydantic_with_schema(self):
        """Pydantic model + Schema: validator comes from Schema, not Pydantic."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from autocrud.crud.core import AutoCRUD

        class PydItem(BaseModel):
            name: str
            price: int

        def custom_check(data):
            if data.price > 9999:
                raise ValueError("too expensive")

        app = AutoCRUD()
        schema = Schema(PydItem, "v1", validator=custom_check)
        app.add_model(schema)
        rm = app.resource_managers["pyd-item"]
        # Since Schema already has a validator, Pydantic should NOT override it
        # The rm._validator should be the Schema's validator
        assert rm._validator is not None

    def test_add_model_pydantic_no_schema_validator_uses_pydantic(self):
        """Pydantic model + Schema without validator: auto-uses Pydantic."""
        pytest.importorskip("pydantic")
        from pydantic import BaseModel

        from autocrud.crud.core import AutoCRUD

        class PydItem2(BaseModel):
            name: str
            price: int

        app = AutoCRUD()
        schema = Schema(PydItem2, "v1")  # no validator
        app.add_model(schema)
        rm = app.resource_managers["pyd-item2"]
        # Pydantic auto-detect should set the validator
        assert rm._validator is not None

    def test_schema_importable_from_autocrud(self):
        """Schema is importable from autocrud package."""
        from autocrud import Schema as S

        assert S is Schema
