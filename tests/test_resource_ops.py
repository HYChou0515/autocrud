"""Tests for ResourceOps — context-capturing proxy returned by ResourceManager.using()."""

import datetime as dt

import pytest
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager, ResourceOps, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore

# ── Test model ──────────────────────────────────────────────────────


class Item(Struct):
    name: str
    value: int = 0


# ── Helpers ─────────────────────────────────────────────────────────

NOW = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
NOW2 = dt.datetime(2025, 6, 15, tzinfo=dt.timezone.utc)


def _make_storage():
    return SimpleStorage(MemoryMetaStore(), MemoryResourceStore())


def make_rm(**kwargs) -> ResourceManager:
    return ResourceManager(Item, storage=_make_storage(), **kwargs)


# ═══════════════════════════════════════════════════════════════════
# Basic usage
# ═══════════════════════════════════════════════════════════════════


class TestBasic:
    """ResourceOps basic create / read / update / delete operations."""

    def test_create_via_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            info = op.create(Item(name="hello"))
        assert info.created_by == "alice"
        assert info.created_time == NOW

    def test_get_via_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            info = op.create(Item(name="hello"))
            res = op.get(info.resource_id)
        assert res.data.name == "hello"

    def test_update_via_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            info = op.create(Item(name="v1"))
            info2 = op.update(info.resource_id, Item(name="v2"))
        res = rm.get(info.resource_id, revision_id=info2.revision_id)
        assert res.data.name == "v2"

    def test_delete_via_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            info = op.create(Item(name="bye"))
            meta = op.delete(info.resource_id)
        assert meta.is_deleted is True

    def test_exists_via_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            info = op.create(Item(name="x"))
            assert op.exists(info.resource_id) is True
            assert op.exists("nonexistent") is False

    def test_get_meta_via_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            info = op.create(Item(name="meta"))
            meta = op.get_meta(info.resource_id)
        assert meta.created_by == "alice"


# ═══════════════════════════════════════════════════════════════════
# Multiple contexts (core feature)
# ═══════════════════════════════════════════════════════════════════


class TestMultipleContexts:
    """Multiple using() scopes on the same RM with independent contexts."""

    def test_two_ops_different_users(self):
        rm = make_rm()
        with (
            rm.using(user="u1", now=NOW) as op1,
            rm.using(user="u2", now=NOW) as op2,
        ):
            info1 = op1.create(Item(name="from_u1"))
            info2 = op2.create(Item(name="from_u2"))

        meta1 = rm.get_meta(info1.resource_id, include_deleted=False)
        meta2 = rm.get_meta(info2.resource_id, include_deleted=False)
        assert meta1.created_by == "u1"
        assert meta2.created_by == "u2"

    def test_two_ops_different_times(self):
        rm = make_rm()
        with (
            rm.using(user="alice", now=NOW) as op1,
            rm.using(user="alice", now=NOW2) as op2,
        ):
            info1 = op1.create(Item(name="early"))
            info2 = op2.create(Item(name="late"))

        meta1 = rm.get_meta(info1.resource_id)
        meta2 = rm.get_meta(info2.resource_id)
        assert meta1.created_time == NOW
        assert meta2.created_time == NOW2

    def test_interleaved_operations(self):
        rm = make_rm()
        with (
            rm.using(user="u1", now=NOW) as op1,
            rm.using(user="u2", now=NOW) as op2,
        ):
            info1 = op1.create(Item(name="a"))
            info2 = op2.create(Item(name="b"))
            # interleave: update with the other user's ops
            op1.update(info1.resource_id, Item(name="a_v2"))
            op2.update(info2.resource_id, Item(name="b_v2"))

        meta1 = rm.get_meta(info1.resource_id)
        meta2 = rm.get_meta(info2.resource_id)
        assert meta1.updated_by == "u1"
        assert meta2.updated_by == "u2"


# ═══════════════════════════════════════════════════════════════════
# resource_id parameter
# ═══════════════════════════════════════════════════════════════════


class TestResourceId:
    """ResourceOps correctly passes captured resource_id."""

    def test_resource_id_captured(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW, resource_id="my-custom-id") as op:
            info = op.create(Item(name="custom"))
        assert info.resource_id == "my-custom-id"


# ═══════════════════════════════════════════════════════════════════
# Deactivation after exit
# ═══════════════════════════════════════════════════════════════════


class TestDeactivation:
    """ResourceOps becomes inactive after the with-block exits."""

    def test_use_after_exit_raises(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            op.create(Item(name="ok"))

        with pytest.raises(RuntimeError, match="no longer active"):
            op.create(Item(name="fail"))

    def test_deactivated_on_exception(self):
        rm = make_rm()
        with pytest.raises(ValueError, match="boom"):
            with rm.using(user="alice", now=NOW) as op:
                raise ValueError("boom")

        with pytest.raises(RuntimeError, match="no longer active"):
            op.create(Item(name="fail"))


# ═══════════════════════════════════════════════════════════════════
# Forbidden rebinding
# ═══════════════════════════════════════════════════════════════════


class TestForbiddenRebinding:
    """Calling using() or meta_provide() on ResourceOps is an error."""

    def test_using_on_ops_raises(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            with pytest.raises(RuntimeError, match="Cannot rebind context"):
                op.using(user="bob")

    def test_meta_provide_on_ops_raises(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            with pytest.raises(RuntimeError, match="Cannot rebind context"):
                op.meta_provide(user="bob")


# ═══════════════════════════════════════════════════════════════════
# Non-callable attribute access
# ═══════════════════════════════════════════════════════════════════


class TestPropertyAccess:
    """ResourceOps proxies non-callable attributes directly."""

    def test_resource_type_access(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            assert op.resource_type is Item

    def test_resource_name_access(self):
        rm = make_rm(name="item")
        with rm.using(user="alice", now=NOW) as op:
            assert op.resource_name == "item"


# ═══════════════════════════════════════════════════════════════════
# Independent RM instances
# ═══════════════════════════════════════════════════════════════════


class TestIndependentManagers:
    """Different RM instances maintain fully independent contexts."""

    def test_two_managers_independent(self):
        rm1 = make_rm()
        rm2 = make_rm()
        with (
            rm1.using(user="u1", now=NOW) as op1,
            rm2.using(user="u2", now=NOW) as op2,
        ):
            info1 = op1.create(Item(name="from_rm1"))
            info2 = op2.create(Item(name="from_rm2"))

        meta1 = rm1.get_meta(info1.resource_id)
        meta2 = rm2.get_meta(info2.resource_id)
        assert meta1.created_by == "u1"
        assert meta2.created_by == "u2"


# ═══════════════════════════════════════════════════════════════════
# Consecutive (non-nested) using() calls
# ═══════════════════════════════════════════════════════════════════


class TestConsecutiveUsing:
    """Sequential using() blocks reuse the same RM cleanly."""

    def test_consecutive_using_works(self):
        rm = make_rm()
        with rm.using(user="first", now=NOW) as op:
            info1 = op.create(Item(name="a"))

        with rm.using(user="second", now=NOW2) as op:
            info2 = op.create(Item(name="b"))

        meta1 = rm.get_meta(info1.resource_id)
        meta2 = rm.get_meta(info2.resource_id)
        assert meta1.created_by == "first"
        assert meta2.created_by == "second"


# ═══════════════════════════════════════════════════════════════════
# Backward compatibility
# ═══════════════════════════════════════════════════════════════════


class TestBackwardCompat:
    """Existing pattern: with rm.using(...): rm.method() still works."""

    def test_old_pattern_without_as(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW):
            info = rm.create(Item(name="compat"))
        assert info.created_by == "alice"

    def test_nested_using_without_as(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW):
            with rm.using(now=NOW2):
                info = rm.create(Item(name="nested"))
        assert info.created_by == "alice"
        assert info.created_time == NOW2


# ═══════════════════════════════════════════════════════════════════
# ResourceOps type identity
# ═══════════════════════════════════════════════════════════════════


class TestTypeIdentity:
    """using() yields a ResourceOps instance, not the manager itself."""

    def test_yields_resource_ops(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            assert isinstance(op, ResourceOps)
            assert op is not rm

    def test_importable_from_autocrud(self):
        from autocrud import ResourceOps as ROps

        assert ROps is ResourceOps
