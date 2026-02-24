"""
Unit tests for UniqueConstraintEventHandler.

These tests verify the handler in isolation (is_supported, before/on_success
lifecycle, thread-local state) as well as integration through ResourceManager.
"""

from __future__ import annotations

import datetime as dt
import threading
from typing import Annotated

import pytest
from jsonpatch import JsonPatch
from msgspec import Struct

from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.resource_manager.unique_handler import (
    UniqueConstraintEventHandler,
    _PhaseState,
)
from autocrud.types import (
    EventContext,
    IndexableField,
    RevisionStatus,
    Unique,
    UniqueConstraintError,
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


def make_rm_with_unique():
    """Create a standard RM with unique Item model."""
    return make_rm(
        Item,
        unique_fields=["name"],
        indexed_fields=[IndexableField(field_path="name", field_type=str)],
    )


# ---------------------------------------------------------------------------
# 1. _PhaseState
# ---------------------------------------------------------------------------


class TestPhaseState:
    def test_initial_state(self):
        state = _PhaseState()
        assert state.needs_post_check is False
        assert state.prev_meta is None
        assert state.prev_info is None
        assert state.current_data is None
        assert state.data is None
        assert state.resource_id is None

    def test_reset_clears_all(self):
        state = _PhaseState()
        state.needs_post_check = True
        state.prev_meta = "something"
        state.data = "data"
        state.resource_id = "rid"
        state.reset()
        assert state.needs_post_check is False
        assert state.prev_meta is None
        assert state.data is None
        assert state.resource_id is None


# ---------------------------------------------------------------------------
# 2. is_supported
# ---------------------------------------------------------------------------


class TestIsSupported:
    def test_supported_for_unique_rm_create_before(self):
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        assert handler is not None
        ctx = _make_before_create(rm, Item(name="x"))
        assert handler.is_supported(ctx) is True

    def test_not_supported_when_no_unique_fields(self):
        rm = make_rm(NoUnique)
        # No handler should be registered
        handlers = [
            h for h in rm.event_handlers if isinstance(h, UniqueConstraintEventHandler)
        ]
        assert handlers == []

    def test_not_supported_for_delete(self):
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        # delete is not in supported actions
        from autocrud.types import BeforeDelete

        ctx = BeforeDelete(
            user="system",
            now=dt.datetime.now(),
            resource_name="item",
            resource_id="rid",
        )
        assert handler.is_supported(ctx) is False

    def test_supported_phases(self):
        """Only 'before' and 'on_success' phases should be supported."""
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        # 'after' and 'on_failure' should not be supported
        from autocrud.types import AfterCreate, OnFailureCreate

        ctx_after = AfterCreate(
            user="system",
            now=dt.datetime.now(),
            resource_name="item",
            data=Item(name="x"),
        )
        assert handler.is_supported(ctx_after) is False
        ctx_fail = OnFailureCreate(
            user="system",
            now=dt.datetime.now(),
            resource_name="item",
            data=Item(name="x"),
            error="boom",
        )
        assert handler.is_supported(ctx_fail) is False

    def test_supported_for_all_actions(self):
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        # Verify supported actions: create, update, modify, switch, restore
        from autocrud.types import (
            BeforeCreate,
            BeforeModify,
            BeforeRestore,
            BeforeSwitch,
            BeforeUpdate,
        )

        now = dt.datetime.now()
        assert (
            handler.is_supported(
                BeforeCreate(
                    user="s", now=now, resource_name="item", data=Item(name="x")
                )
            )
            is True
        )
        assert (
            handler.is_supported(
                BeforeUpdate(
                    user="s",
                    now=now,
                    resource_name="item",
                    resource_id="r",
                    data=Item(name="x"),
                )
            )
            is True
        )
        assert (
            handler.is_supported(
                BeforeModify(user="s", now=now, resource_name="item", resource_id="r")
            )
            is True
        )
        assert (
            handler.is_supported(
                BeforeSwitch(
                    user="s",
                    now=now,
                    resource_name="item",
                    resource_id="r",
                    revision_id="rv",
                )
            )
            is True
        )
        assert (
            handler.is_supported(
                BeforeRestore(user="s", now=now, resource_name="item", resource_id="r")
            )
            is True
        )


# ---------------------------------------------------------------------------
# 3. Before phase — create
# ---------------------------------------------------------------------------


class TestBeforeCreate:
    def test_precheck_blocks_duplicate(self):
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError) as exc:
            rm.create(Item(name="alpha"))
        assert exc.value.field == "name"
        assert exc.value.value == "alpha"

    def test_precheck_allows_unique(self):
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        info = rm.create(Item(name="beta"))
        assert info.resource_id is not None


# ---------------------------------------------------------------------------
# 4. Before phase — update
# ---------------------------------------------------------------------------


class TestBeforeUpdate:
    def test_update_same_value_ok(self):
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"))
        info2 = rm.update(info.resource_id, Item(name="alpha", value=99))
        assert info2 is not None

    def test_update_conflict_raises(self):
        rm = make_rm_with_unique()
        info_a = rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"))
        with pytest.raises(UniqueConstraintError):
            rm.update(info_b.resource_id, Item(name="alpha"))


# ---------------------------------------------------------------------------
# 5. Before phase — modify
# ---------------------------------------------------------------------------


class TestBeforeModify:
    def test_modify_unset_data_skips(self):
        """Modify with UNSET data should not trigger unique check."""
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"), status=RevisionStatus.draft)
        # modify with only status change
        info2 = rm.modify(info.resource_id, status=RevisionStatus.draft)
        assert info2 is not None

    def test_modify_same_unique_value_ok(self):
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"), status=RevisionStatus.draft)
        info2 = rm.modify(info.resource_id, Item(name="alpha", value=5))
        assert info2 is not None

    def test_modify_conflict_raises(self):
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"), status=RevisionStatus.draft)
        with pytest.raises(UniqueConstraintError):
            rm.modify(info_b.resource_id, Item(name="alpha"))

    def test_modify_unchanged_unique_field_no_check(self):
        """When only non-unique fields change, no constraint check should run."""
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"), status=RevisionStatus.draft)
        # Only change value, not name → should not raise
        info2 = rm.modify(info_b.resource_id, Item(name="beta", value=99))
        assert info2 is not None


# ---------------------------------------------------------------------------
# 6. Before phase — switch
# ---------------------------------------------------------------------------


class TestBeforeSwitch:
    def test_switch_conflict_raises(self):
        rm = make_rm_with_unique()
        info_v1 = rm.create(Item(name="alpha"))
        rid = info_v1.resource_id
        rm.update(rid, Item(name="beta"))
        # Another resource takes 'alpha'
        rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError):
            rm.switch(rid, info_v1.revision_id)

    def test_switch_no_conflict_ok(self):
        rm = make_rm_with_unique()
        info_v1 = rm.create(Item(name="alpha"))
        rid = info_v1.resource_id
        rm.update(rid, Item(name="beta"))
        meta = rm.switch(rid, info_v1.revision_id)
        assert meta.current_revision_id == info_v1.revision_id

    def test_switch_same_revision_noop(self):
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"))
        meta = rm.switch(info.resource_id, info.revision_id)
        assert meta.current_revision_id == info.revision_id


# ---------------------------------------------------------------------------
# 7. Before phase — restore
# ---------------------------------------------------------------------------


class TestBeforeRestore:
    def test_restore_conflict_raises(self):
        rm = make_rm_with_unique()
        info_a = rm.create(Item(name="alpha"))
        rm.delete(info_a.resource_id)
        rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError):
            rm.restore(info_a.resource_id)

    def test_restore_no_conflict_ok(self):
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"))
        rm.delete(info.resource_id)
        meta = rm.restore(info.resource_id)
        assert meta.is_deleted is False

    def test_restore_not_deleted_noop(self):
        """Restoring a non-deleted resource should be a no-op (no check)."""
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"))
        meta = rm.restore(info.resource_id)
        assert meta.is_deleted is False


# ---------------------------------------------------------------------------
# 8. On-success phase — create post-check + compensate
# ---------------------------------------------------------------------------


class TestPostCheckCreate:
    def test_create_compensate_hard_purge(self):
        """When post-check fails, the resource should be hard-purged."""
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        # Second create should fail
        with pytest.raises(UniqueConstraintError):
            rm.create(Item(name="alpha"))
        # After compensation, the second resource should not exist
        # Only one resource should exist
        from autocrud.types import ResourceMetaSearchQuery

        results = rm.storage.search(ResourceMetaSearchQuery(is_deleted=False))
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 9. On-success phase — update post-check + compensate
# ---------------------------------------------------------------------------


class TestPostCheckUpdate:
    def test_update_restore_prev_meta_on_conflict(self):
        """After update post-check conflict, resource should retain previous state."""
        rm = make_rm_with_unique()
        info_a = rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"))
        with pytest.raises(UniqueConstraintError):
            rm.update(info_b.resource_id, Item(name="alpha"))
        # Resource B should still have its original meta
        meta_b = rm.get_meta(info_b.resource_id)
        assert meta_b.current_revision_id == info_b.revision_id


# ---------------------------------------------------------------------------
# 10. On-success phase — modify post-check + compensate
# ---------------------------------------------------------------------------


class TestPostCheckModify:
    def test_modify_compensate_restores_state(self):
        """After modify post-check conflict, resource should retain previous data."""
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"), status=RevisionStatus.draft)
        with pytest.raises(UniqueConstraintError):
            rm.modify(info_b.resource_id, Item(name="alpha"))
        # Resource B should still have name="beta"
        res = rm.get(info_b.resource_id)
        assert res.data.name == "beta"


# ---------------------------------------------------------------------------
# 11. On-success phase — switch post-check + compensate
# ---------------------------------------------------------------------------


class TestPostCheckSwitch:
    def test_switch_compensate_restores_meta(self):
        """After switch post-check conflict, meta should be reverted."""
        rm = make_rm_with_unique()
        info_v1 = rm.create(Item(name="alpha"))
        rid = info_v1.resource_id
        info_v2 = rm.update(rid, Item(name="beta"))
        # Another takes 'alpha'
        rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError):
            rm.switch(rid, info_v1.revision_id)
        # Resource should still point to v2
        meta = rm.get_meta(rid)
        assert meta.current_revision_id == info_v2.revision_id


# ---------------------------------------------------------------------------
# 12. On-success phase — restore post-check + compensate
# ---------------------------------------------------------------------------


class TestPostCheckRestore:
    def test_restore_compensate_re_deletes(self):
        """After restore post-check conflict, resource should be re-deleted."""
        rm = make_rm_with_unique()
        info_a = rm.create(Item(name="alpha"))
        rm.delete(info_a.resource_id)
        rm.create(Item(name="alpha"))
        with pytest.raises(UniqueConstraintError):
            rm.restore(info_a.resource_id)
        # Resource A should still be deleted
        meta = rm._get_meta_no_check_is_deleted(info_a.resource_id)
        assert meta.is_deleted is True


# ---------------------------------------------------------------------------
# 13. Thread-local state isolation
# ---------------------------------------------------------------------------


class TestThreadLocalIsolation:
    def test_concurrent_creates_no_state_leak(self):
        """State from one thread should not leak to another."""
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        results = {}
        barrier = threading.Barrier(2, timeout=5)

        def create_in_thread(name, key):
            try:
                barrier.wait()
                info = rm.create(Item(name=name))
                results[key] = ("ok", info.resource_id)
            except UniqueConstraintError as e:
                results[key] = ("conflict", str(e))
            except Exception as e:
                results[key] = ("error", str(e))

        t1 = threading.Thread(target=create_in_thread, args=("t1_unique", "t1"))
        t2 = threading.Thread(target=create_in_thread, args=("t2_unique", "t2"))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert results["t1"][0] == "ok"
        assert results["t2"][0] == "ok"

    def test_state_reset_after_success(self):
        """Thread-local state should be reset after on_success."""
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        rm.create(Item(name="alpha"))
        state = handler._get_state()
        assert state.needs_post_check is False
        assert state.data is None


# ---------------------------------------------------------------------------
# 14. Handler internal helpers
# ---------------------------------------------------------------------------


class TestHandlerHelpers:
    def test_unique_fields_changed_true(self):
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        assert (
            handler._unique_fields_changed(Item(name="alpha"), Item(name="beta"))
            is True
        )

    def test_unique_fields_changed_false(self):
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        assert (
            handler._unique_fields_changed(
                Item(name="alpha", value=1), Item(name="alpha", value=2)
            )
            is False
        )

    def test_check_unique_constraints_no_fields(self):
        """_check_unique_constraints should be a no-op when no unique fields."""
        rm = make_rm(NoUnique)
        handler = UniqueConstraintEventHandler(rm)
        # Should not raise
        handler._check_unique_constraints(NoUnique(name="alpha"))

    def test_check_unique_constraints_none_value_skipped(self):
        """None values should be skipped (no uniqueness check for None)."""

        class OptionalUnique(Struct):
            name: Annotated[str | None, Unique()] = None
            value: int = 0

        rm = make_rm(
            OptionalUnique,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )
        handler = _get_handler(rm)
        # Create with None name — should succeed even if called multiple times
        rm.create(OptionalUnique(name=None, value=1))
        rm.create(OptionalUnique(name=None, value=2))

    def test_hard_purge_resource(self):
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        info = rm.create(Item(name="alpha"))
        rid = info.resource_id
        assert rm.storage.exists(rid)
        handler._hard_purge_resource(rid)
        assert not rm.storage.exists(rid)

    def test_hard_purge_nonexistent_noop(self):
        """Purging a non-existent resource should not raise."""
        rm = make_rm_with_unique()
        handler = _get_handler(rm)
        handler._hard_purge_resource("nonexistent")  # should not raise


# ---------------------------------------------------------------------------
# 15. Handler registered correctly
# ---------------------------------------------------------------------------


class TestHandlerRegistration:
    def test_handler_is_last(self):
        """UniqueConstraintEventHandler should be the last handler."""
        rm = make_rm_with_unique()
        assert len(rm.event_handlers) >= 1
        assert isinstance(rm.event_handlers[-1], UniqueConstraintEventHandler)

    def test_handler_after_permission(self):
        """UniqueConstraintEventHandler should come after PermissionEventHandler."""
        from autocrud.permission.simple import AllowAll
        from autocrud.resource_manager.core import PermissionEventHandler

        rm = make_rm(
            Item,
            unique_fields=["name"],
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
        )
        # create with permission checker
        storage = MemoryStorageFactory().build("test")
        rm2 = ResourceManager(
            Item,
            storage=storage,
            indexed_fields=[IndexableField(field_path="name", field_type=str)],
            unique_fields=["name"],
            permission_checker=AllowAll(),
            default_user="system",
            default_now=dt.datetime.now,
        )
        perm_idx = None
        unique_idx = None
        for i, h in enumerate(rm2.event_handlers):
            if isinstance(h, PermissionEventHandler):
                perm_idx = i
            if isinstance(h, UniqueConstraintEventHandler):
                unique_idx = i
        assert perm_idx is not None
        assert unique_idx is not None
        assert perm_idx < unique_idx

    def test_no_handler_when_no_unique_fields(self):
        rm = make_rm(NoUnique)
        handlers = [
            h for h in rm.event_handlers if isinstance(h, UniqueConstraintEventHandler)
        ]
        assert handlers == []


# ---------------------------------------------------------------------------
# 16. Multi-unique field support
# ---------------------------------------------------------------------------


class TestMultiUnique:
    def test_multi_unique_both_enforced(self):
        rm = make_rm(
            MultiUnique,
            unique_fields=["code", "slug"],
            indexed_fields=[
                IndexableField(field_path="code", field_type=str),
                IndexableField(field_path="slug", field_type=str),
            ],
        )
        rm.create(MultiUnique(code="c1", slug="s1"))
        # Same code → conflict
        with pytest.raises(UniqueConstraintError) as exc:
            rm.create(MultiUnique(code="c1", slug="s2"))
        assert exc.value.field == "code"
        # Same slug → conflict
        with pytest.raises(UniqueConstraintError) as exc:
            rm.create(MultiUnique(code="c2", slug="s1"))
        assert exc.value.field == "slug"
        # Both different → OK
        rm.create(MultiUnique(code="c2", slug="s2"))


# ---------------------------------------------------------------------------
# 17. Modify with JsonPatch
# ---------------------------------------------------------------------------


class TestModifyJsonPatch:
    def test_modify_jsonpatch_unique_conflict(self):
        """Modify via JsonPatch changing unique field to conflicting value."""
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"), status=RevisionStatus.draft)
        patch = JsonPatch([{"op": "replace", "path": "/name", "value": "alpha"}])
        with pytest.raises(UniqueConstraintError):
            rm.modify(info_b.resource_id, patch)

    def test_modify_jsonpatch_no_conflict(self):
        """Modify via JsonPatch changing unique field to unused value."""
        rm = make_rm_with_unique()
        info = rm.create(Item(name="alpha"), status=RevisionStatus.draft)
        patch = JsonPatch([{"op": "replace", "path": "/name", "value": "gamma"}])
        info2 = rm.modify(info.resource_id, patch)
        assert info2 is not None
        res = rm.get(info.resource_id)
        assert res.data.name == "gamma"

    def test_modify_jsonpatch_non_unique_field(self):
        """Modify via JsonPatch changing only non-unique fields should not raise."""
        rm = make_rm_with_unique()
        rm.create(Item(name="alpha"))
        info_b = rm.create(Item(name="beta"), status=RevisionStatus.draft)
        patch = JsonPatch([{"op": "replace", "path": "/value", "value": 99}])
        info2 = rm.modify(info_b.resource_id, patch)
        assert info2 is not None


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _get_handler(rm: ResourceManager) -> UniqueConstraintEventHandler | None:
    """Extract the UniqueConstraintEventHandler from an RM's event_handlers."""
    for h in rm.event_handlers:
        if isinstance(h, UniqueConstraintEventHandler):
            return h
    return None


def _make_before_create(rm: ResourceManager, data) -> EventContext:
    from autocrud.types import BeforeCreate

    return BeforeCreate(
        user="system",
        now=dt.datetime.now(),
        resource_name=rm.resource_name,
        data=data,
    )
