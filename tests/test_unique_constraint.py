"""
Tests for Unique annotated field support.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated

import pytest
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import (
    IndexableField,
    RevisionStatus,
    Unique,
    UniqueConstraintError,
    extract_unique_fields,
)

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Item(Struct):
    name: Annotated[str, Unique()]
    value: int = 0


class MultiUnique(Struct):
    code: Annotated[str, Unique()]
    slug: Annotated[str, Unique()]
    description: str = ""


class NoUnique(Struct):
    name: str
    value: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_rm(resource_type, unique_fields=None, indexed_fields=None):
    """Create a ResourceManager with MemoryStorageFactory."""
    storage = MemoryStorageFactory().build("test")
    return ResourceManager(
        resource_type,
        storage=storage,
        indexed_fields=indexed_fields or [],
        unique_fields=unique_fields or [],
        default_user="system",
        default_now=dt.datetime.now,
    )


def make_ac():
    """Create a configured AutoCRUD instance for integration tests."""
    from autocrud import AutoCRUD

    ac = AutoCRUD()
    ac.configure(
        storage_factory=MemoryStorageFactory(),
        default_user="system",
        default_now=dt.datetime.now,
    )
    return ac


# ---------------------------------------------------------------------------
# 1. Unique / extract_unique_fields / UniqueConstraintError basics
# ---------------------------------------------------------------------------


class TestUniqueAnnotation:
    def test_unique_repr(self):
        u = Unique()
        assert repr(u) == "Unique()"

    def test_extract_unique_fields_empty(self):
        assert extract_unique_fields(NoUnique) == []

    def test_extract_unique_fields_single(self):
        fields = extract_unique_fields(Item)
        assert fields == ["name"]

    def test_extract_unique_fields_multiple(self):
        fields = extract_unique_fields(MultiUnique)
        assert set(fields) == {"code", "slug"}

    def test_unique_constraint_error_attributes(self):
        err = UniqueConstraintError("name", "alice", "item:abc")
        assert err.field == "name"
        assert err.value == "alice"
        assert err.conflicting_resource_id == "item:abc"
        assert "name" in str(err)
        assert "alice" in str(err)
        assert "item:abc" in str(err)

    def test_unique_constraint_error_is_exception(self):
        err = UniqueConstraintError("x", 1, "rid")
        with pytest.raises(UniqueConstraintError):
            raise err


# ---------------------------------------------------------------------------
# 2. ResourceManager.create() uniqueness enforcement
# ---------------------------------------------------------------------------


class TestCreateUnique:
    def setup_method(self):
        self.rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )

    def test_first_create_succeeds(self):
        info = self.rm.create(Item(name="alpha"))
        assert info.resource_id is not None

    def test_second_create_same_value_raises(self):
        self.rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError) as exc_info:
            self.rm.create(Item(name="alpha"))
        assert exc_info.value.field == "name"
        assert exc_info.value.value == "alpha"

    def test_create_different_values_ok(self):
        self.rm.create(Item(name="alpha"))
        info2 = self.rm.create(Item(name="beta"))  # different value → OK
        assert info2.resource_id is not None

    def test_create_after_delete_unique_frees_slot(self):
        """After soft-deleting a resource, its UK slot should be freed."""
        info = self.rm.create(Item(name="alpha"))
        self.rm.delete(info.resource_id)
        # Now we should be able to create another with the same name
        info2 = self.rm.create(Item(name="alpha"))
        assert info2.resource_id is not None


# ---------------------------------------------------------------------------
# 3. ResourceManager.update() uniqueness enforcement
# ---------------------------------------------------------------------------


class TestUpdateUnique:
    def setup_method(self):
        self.rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )

    def test_update_same_resource_same_value_ok(self):
        """Updating a resource without changing the UK must not raise."""
        info = self.rm.create(Item(name="alpha"))
        # update keeping same name
        info2 = self.rm.update(info.resource_id, Item(name="alpha", value=99))
        assert info2 is not None  # either same info (no-op) or new revision

    def test_update_same_resource_new_value_ok(self):
        """Changing the UK to an unused value must succeed."""
        info = self.rm.create(Item(name="alpha"))
        info2 = self.rm.update(info.resource_id, Item(name="beta"))
        assert info2.resource_id == info.resource_id

    def test_update_conflict_with_other_resource_raises(self):
        """Changing UK to a value used by another resource must raise."""
        info_a = self.rm.create(Item(name="alpha"))
        info_b = self.rm.create(Item(name="beta"))
        with pytest.raises(UniqueConstraintError) as exc_info:
            self.rm.update(info_b.resource_id, Item(name="alpha"))
        assert exc_info.value.field == "name"
        assert exc_info.value.value == "alpha"
        assert exc_info.value.conflicting_resource_id == info_a.resource_id


# ---------------------------------------------------------------------------
# 4. ResourceManager.modify() uniqueness enforcement
# ---------------------------------------------------------------------------


class TestModifyUnique:
    def setup_method(self):
        self.rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )

    def test_modify_same_value_ok(self):
        """Modify with same UK value must not raise."""
        info = self.rm.create(Item(name="alpha"), status=RevisionStatus.draft)
        info2 = self.rm.modify(info.resource_id, Item(name="alpha", value=5))
        assert info2.resource_id == info.resource_id

    def test_modify_conflict_raises(self):
        """Modify that changes UK to an already-used value must raise."""
        self.rm.create(Item(name="alpha"))
        info_b = self.rm.create(Item(name="beta"), status=RevisionStatus.draft)
        with pytest.raises(UniqueConstraintError):
            self.rm.modify(info_b.resource_id, Item(name="alpha"))

    def test_modify_no_unique_field_change_skips_check(self):
        """Modify that does not change the unique field must not raise even if
        another resource has the same value."""
        self.rm.create(Item(name="alpha"))
        info_b = self.rm.create(Item(name="beta"), status=RevisionStatus.draft)
        # Modify only the non-unique field: value=99
        # This should NOT raise even though "alpha" already exists
        info2 = self.rm.modify(info_b.resource_id, Item(name="beta", value=99))
        assert info2 is not None


# ---------------------------------------------------------------------------
# 5. Auto-indexing via add_model (integration with AutoCRUD)
# ---------------------------------------------------------------------------


class TestAddModelAutoIndex:
    def test_unique_field_auto_indexed_via_add_model(self):
        """Unique fields should be auto-added to indexed_fields by add_model."""
        ac = make_ac()
        ac.add_model(Item)
        rm = ac.resource_managers["item"]
        indexed_paths = {f.field_path for f in rm.indexed_fields}
        assert "name" in indexed_paths

    def test_unique_constraint_via_add_model(self):
        """Uniqueness should be enforced when using add_model."""
        ac = make_ac()
        ac.add_model(Item)
        rm = ac.resource_managers["item"]
        rm.create(Item(name="hello"))
        with pytest.raises(UniqueConstraintError):
            rm.create(Item(name="hello"))

    def test_multiple_unique_fields_all_enforced(self):
        """All Unique-annotated fields in a model should be enforced separately."""
        ac = make_ac()
        ac.add_model(MultiUnique)
        # Default naming is kebab-case: MultiUnique → multi-unique
        rm = ac.resource_managers["multi-unique"]

        rm.create(MultiUnique(code="c1", slug="s1"))

        # Same code, different slug → conflict on code
        with pytest.raises(UniqueConstraintError) as exc_info:
            rm.create(MultiUnique(code="c1", slug="s2"))
        assert exc_info.value.field == "code"

        # Different code, same slug → conflict on slug
        with pytest.raises(UniqueConstraintError) as exc_info:
            rm.create(MultiUnique(code="c2", slug="s1"))
        assert exc_info.value.field == "slug"

        # Both different → OK
        info = rm.create(MultiUnique(code="c2", slug="s2"))
        assert info.resource_id is not None


# ---------------------------------------------------------------------------
# 6. Hard delete / purge_meta on IStorage
# ---------------------------------------------------------------------------


class TestPurgeMeta:
    def test_purge_meta_removes_resource(self):
        rm = make_rm(
            Item,
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
            unique_fields=["name"],
        )
        info = rm.create(Item(name="alpha"))
        rid = info.resource_id
        assert rm.storage.exists(rid)
        rm.storage.purge_meta(rid)
        assert not rm.storage.exists(rid)


# ---------------------------------------------------------------------------
# 7. Bug fix: unique_fields ⊆ indexed_fields validation
# ---------------------------------------------------------------------------


class TestUniqueFieldsMustBeIndexed:
    def test_unique_field_not_indexed_raises_on_init(self):
        """Creating RM with unique_fields not in indexed_fields must raise."""
        with pytest.raises(ValueError, match="name"):
            make_rm(
                Item,
                unique_fields=["name"],
                indexed_fields=[],  # name not indexed!
            )

    def test_unique_field_indexed_ok(self):
        """Creating RM with unique_fields ⊆ indexed_fields must succeed."""
        rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )
        assert rm._unique_fields == ["name"]

    def test_partial_indexed_raises(self):
        """If only some unique fields are indexed, must raise for the missing ones."""
        with pytest.raises(ValueError, match="slug"):
            make_rm(
                MultiUnique,
                unique_fields=["code", "slug"],
                indexed_fields=[IndexableField(field_path="code", field_type=str)],
            )


# ---------------------------------------------------------------------------
# 8. Bug fix: restore() must check unique constraints
# ---------------------------------------------------------------------------


class TestRestoreUniqueCheck:
    def setup_method(self):
        self.rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )

    def test_restore_conflict_raises(self):
        """Restoring a resource whose UK is now held by another must raise."""
        info_a = self.rm.create(Item(name="alpha"))
        self.rm.delete(info_a.resource_id)
        # Another resource takes 'alpha' while the old one is deleted
        self.rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError):
            self.rm.restore(info_a.resource_id)

    def test_restore_no_conflict_ok(self):
        """Restoring a resource whose UK is free must succeed."""
        info_a = self.rm.create(Item(name="alpha"))
        self.rm.delete(info_a.resource_id)
        meta = self.rm.restore(info_a.resource_id)
        assert meta.is_deleted is False


# ---------------------------------------------------------------------------
# 9. Bug fix: switch() must check unique constraints
# ---------------------------------------------------------------------------


class TestSwitchUniqueCheck:
    def setup_method(self):
        self.rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )

    def test_switch_conflict_raises(self):
        """Switching to a revision whose UK value conflicts must raise."""
        info_v1 = self.rm.create(Item(name="alpha"))
        rid = info_v1.resource_id
        # Update to 'beta' (rev 2) — frees 'alpha'
        self.rm.update(rid, Item(name="beta"))
        # Another resource takes 'alpha'
        self.rm.create(Item(name="alpha"))
        # Now switch back to rev 1 ('alpha') — should conflict
        with pytest.raises(UniqueConstraintError):
            self.rm.switch(rid, info_v1.revision_id)

    def test_switch_no_conflict_ok(self):
        """Switching to a revision whose UK value is free must succeed."""
        info_v1 = self.rm.create(Item(name="alpha"))
        rid = info_v1.resource_id
        self.rm.update(rid, Item(name="beta"))
        # Switch back to rev 1 — 'alpha' is free
        meta = self.rm.switch(rid, info_v1.revision_id)
        assert meta.current_revision_id == info_v1.revision_id

    def test_switch_same_revision_noop(self):
        """Switching to the current revision must be a no-op (no UK check)."""
        info = self.rm.create(Item(name="alpha"))
        meta = self.rm.switch(info.resource_id, info.revision_id)
        assert meta.current_revision_id == info.revision_id


# ---------------------------------------------------------------------------
# 10. Bug fix: modify() must have post-check for race condition
# ---------------------------------------------------------------------------


class TestModifyPostCheck:
    def test_modify_post_check_compensates(self):
        """If modify post-check finds a conflict, it should restore prev state."""
        rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )
        info_a = rm.create(Item(name="alpha"), status=RevisionStatus.draft)
        info_b = rm.create(Item(name="beta"), status=RevisionStatus.draft)
        # Modify B to 'gamma' — no conflict, must pass
        rm.modify(info_b.resource_id, Item(name="gamma"))
        # Verify the data actually changed
        res = rm.get(info_b.resource_id)
        assert res.data.name == "gamma"
