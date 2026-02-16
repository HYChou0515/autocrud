"""Tests for ResourceManager data coercion (pydantic_type aware).

When RM is constructed with ``pydantic_type``:
- Input:  accepts Pydantic instance / dict → internally stored as Struct
- Output: always Struct (required for msgspec serialization in API routes)

When RM is constructed WITHOUT ``pydantic_type`` (default):
- Input:  accepts Struct / dict
- Output: returns Struct (existing behaviour)
"""

import datetime as dt

import pytest
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.pydantic_converter import pydantic_to_struct
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import RevisionStatus, ValidationError

# ===== Test Models =====


class Item(Struct):
    name: str
    price: int
    quantity: int = 0
    description: str = ""


def make_mgr(resource_type=Item, **kwargs) -> ResourceManager:
    """Create a ResourceManager with memory storage."""
    storage = MemoryStorageFactory().build("test")
    return ResourceManager(resource_type, storage=storage, **kwargs)


# =====================================================================
# 1. Dict Coercion (no pydantic_type — existing behaviour)
# =====================================================================


class TestDictCoercion:
    """ResourceManager should accept dict and convert to Struct."""

    def test_create_with_dict(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create({"name": "Sword", "price": 100})
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Sword"
        assert resource.data.price == 100
        assert resource.data.quantity == 0  # default
        assert isinstance(resource.data, Struct)

    def test_create_with_dict_and_defaults(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create({"name": "Shield", "price": 50, "quantity": 3})
        resource = mgr.get(info.resource_id)
        assert resource.data.quantity == 3
        assert resource.data.description == ""

    def test_update_with_dict(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
            mgr.update(info.resource_id, {"name": "Great Sword", "price": 200})
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Great Sword"
        assert resource.data.price == 200

    def test_modify_with_dict(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(
                Item(name="Sword", price=100), status=RevisionStatus.draft
            )
            mgr.modify(info.resource_id, {"name": "Better Sword", "price": 150})
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Better Sword"

    def test_create_or_update_with_dict(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
            mgr.create_or_update(
                info.resource_id, {"name": "Updated Sword", "price": 200}
            )
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Updated Sword"

    def test_create_with_dict_extra_field_ignored(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create({"name": "Sword", "price": 100, "nonexistent": True})
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Sword"
        assert resource.data.price == 100

    def test_create_with_dict_missing_required_field_raises(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(Exception):
                mgr.create({"name": "Sword"})  # missing 'price'

    def test_create_with_dict_and_validator(self):
        def check_price(data: Item) -> None:
            if data.price < 0:
                raise ValueError("Price must be non-negative")

        mgr = make_mgr(validator=check_price)
        with mgr.meta_provide("user", dt.datetime.now()):
            with pytest.raises(ValidationError, match="Price must be non-negative"):
                mgr.create({"name": "Bad", "price": -1})

    def test_struct_instance_still_works(self):
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Sword"
        assert isinstance(resource.data, Struct)


# =====================================================================
# 2. Pydantic Mode — RM constructed with pydantic_type
# =====================================================================


class TestPydanticMode:
    """When RM has pydantic_type set, inputs accept Pydantic instances.
    Outputs are always Struct (required for msgspec serialization)."""

    @pytest.fixture(autouse=True)
    def setup(self):
        pydantic = pytest.importorskip("pydantic")
        self.BaseModel = pydantic.BaseModel

    def _make_pydantic_model(self):
        """Create a simple Pydantic model and its corresponding Struct."""

        class ItemModel(self.BaseModel):
            name: str
            price: int
            quantity: int = 0
            description: str = ""

        return ItemModel

    def _make_pydantic_mgr(self, pydantic_model=None, **kwargs):
        """Create an RM configured for pydantic mode."""
        if pydantic_model is None:
            pydantic_model = self._make_pydantic_model()
        struct_type = pydantic_to_struct(pydantic_model)
        return make_mgr(
            resource_type=struct_type,
            pydantic_type=pydantic_model,
            **kwargs,
        ), pydantic_model

    # --- Input: create with Pydantic instance ---
    def test_create_with_pydantic_instance(self):
        mgr, Model = self._make_pydantic_mgr()
        item = Model(name="Sword", price=100)
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(item)
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Sword"
        assert resource.data.price == 100
        assert isinstance(resource.data, Struct)  # always Struct

    # --- Input: create with dict in pydantic mode ---
    def test_create_with_dict_in_pydantic_mode(self):
        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create({"name": "Shield", "price": 50})
        resource = mgr.get(info.resource_id)
        assert resource.data.name == "Shield"
        assert isinstance(resource.data, Struct)

    # --- Output: get returns Struct with correct values ---
    def test_get_returns_struct_with_correct_values(self):
        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Model(name="Bow", price=80))
        resource = mgr.get(info.resource_id)
        assert isinstance(resource.data, Struct)
        assert resource.data.name == "Bow"
        assert resource.data.price == 80
        assert resource.data.quantity == 0

    # --- Output: get_resource_revision returns Struct ---
    def test_get_resource_revision_returns_struct(self):
        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Model(name="Staff", price=120))
        resource = mgr.get_resource_revision(info.resource_id, info.revision_id)
        assert isinstance(resource.data, Struct)
        assert resource.data.name == "Staff"

    # --- Input: update with Pydantic ---
    def test_update_with_pydantic_instance(self):
        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Model(name="Sword", price=100))
            mgr.update(info.resource_id, Model(name="Great Sword", price=200))
        resource = mgr.get(info.resource_id)
        assert isinstance(resource.data, Struct)
        assert resource.data.name == "Great Sword"
        assert resource.data.price == 200

    # --- Input: modify with Pydantic ---
    def test_modify_with_pydantic_instance(self):
        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(
                Model(name="Sword", price=100), status=RevisionStatus.draft
            )
            mgr.modify(info.resource_id, Model(name="Better Sword", price=150))
        resource = mgr.get(info.resource_id)
        assert isinstance(resource.data, Struct)
        assert resource.data.name == "Better Sword"

    # --- Validator still works in pydantic mode ---
    def test_pydantic_validator_works(self):
        """Pydantic model used as validator should reject invalid data."""
        from pydantic import field_validator

        class StrictItem(self.BaseModel):
            name: str
            price: int
            quantity: int = 0
            description: str = ""

            @field_validator("price")
            @classmethod
            def price_must_be_positive(cls, v):
                if v < 0:
                    raise ValueError("Price must be non-negative")
                return v

        mgr, _ = self._make_pydantic_mgr(
            pydantic_model=StrictItem, validator=StrictItem
        )
        with mgr.meta_provide("user", dt.datetime.now()):
            # Pass dict to bypass Pydantic's eager construction validation,
            # so the RM validator (which uses pydantic_to_validator) catches it.
            with pytest.raises(ValidationError):
                mgr.create({"name": "Bad", "price": -1})

    # --- Non-pydantic mode still returns Struct ---
    def test_non_pydantic_mode_returns_struct(self):
        """Without pydantic_type, get still returns Struct."""
        mgr = make_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Item(name="Sword", price=100))
        resource = mgr.get(info.resource_id)
        assert isinstance(resource.data, Struct)
        assert not isinstance(resource.data, self.BaseModel)

    # --- API serialization: data must be msgspec-encodable ---
    def test_get_data_is_msgspec_serializable(self):
        """get() data must be serializable by msgspec.json.encode,
        because MsgspecResponse in API routes calls msgspec.json.encode(data).
        Regression test for: 'Encoding objects of type X is unsupported'."""
        import msgspec as _msgspec

        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Model(name="Sword", price=100))
        resource = mgr.get(info.resource_id)
        # Must not raise "Encoding objects of type ... is unsupported"
        _msgspec.json.encode(resource.data)

    def test_get_resource_revision_data_is_msgspec_serializable(self):
        """get_resource_revision() data must be msgspec-serializable."""
        import msgspec as _msgspec

        mgr, Model = self._make_pydantic_mgr()
        with mgr.meta_provide("user", dt.datetime.now()):
            info = mgr.create(Model(name="Staff", price=120))
        resource = mgr.get_resource_revision(info.resource_id, info.revision_id)
        _msgspec.json.encode(resource.data)
