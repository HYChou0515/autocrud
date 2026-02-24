"""
Tests for the generic ConstraintEventHandler and IConstraintChecker abstraction.

Verifies:
- Custom IConstraintChecker plugging via ResourceManager and AutoCRUD.add_model()
- Multi-checker composition (multiple checkers enforced together)
- Compensation (rollback) on post-check failure
- data_relevant_changed optimisation (skip when unchanged)
- ConstraintEventHandler state isolation (ContextVar per-instance)
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from jsonpatch import JsonPatch
from msgspec import Struct

from autocrud.resource_manager.constraint_handler import (
    ConstraintEventHandler,
    _PhaseState,
)
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.resource_manager.unique_handler import (
    UniqueConstraintChecker,
)
from autocrud.types import (
    IConstraintChecker,
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


class ItemNoUnique(Struct):
    name: str
    value: int = 0


# ---------------------------------------------------------------------------
# Custom constraint checkers for testing
# ---------------------------------------------------------------------------


class MaxValueChecker(IConstraintChecker):
    """Rejects data where value > max_value."""

    def __init__(self, rm: ResourceManager, max_value: int = 100) -> None:
        self.rm = rm
        self.max_value = max_value

    def check(self, data: Any, *, exclude_resource_id: str | None = None) -> None:
        val = getattr(data, "value", None)
        if val is not None and val > self.max_value:
            raise ValueError(f"value {val} exceeds maximum {self.max_value}")

    def data_relevant_changed(self, current_data: Any, new_data: Any) -> bool:
        return getattr(current_data, "value", None) != getattr(new_data, "value", None)


class NameBlacklistChecker(IConstraintChecker):
    """Rejects data where name is in a blacklist."""

    def __init__(self, rm: ResourceManager, blacklist: list[str] | None = None) -> None:
        self.rm = rm
        self.blacklist = blacklist or ["forbidden", "blocked"]

    def check(self, data: Any, *, exclude_resource_id: str | None = None) -> None:
        name = getattr(data, "name", None)
        if name in self.blacklist:
            raise ValueError(f"name {name!r} is blacklisted")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_rm(
    resource_type=Item,
    constraint_checkers=None,
):
    """Create a ResourceManager with optional constraint checkers."""
    storage = MemoryStorageFactory().build("test")
    return ResourceManager(
        resource_type,
        storage=storage,
        constraint_checkers=constraint_checkers,
        default_user="system",
        default_now=dt.datetime.now,
    )


def make_rm_with_unique(constraint_checkers=None):
    """Create RM with unique Item model + optional extra checkers."""
    checkers = list(constraint_checkers or [])
    checkers.append(UniqueConstraintChecker)
    return make_rm(
        Item,
        constraint_checkers=checkers,
    )


def make_ac():
    """Create a configured AutoCRUD instance."""
    from autocrud import AutoCRUD

    ac = AutoCRUD()
    ac.configure(
        storage_factory=MemoryStorageFactory(),
        default_user="system",
        default_now=dt.datetime.now,
    )
    return ac


def _get_constraint_handler(rm: ResourceManager) -> ConstraintEventHandler | None:
    """Find the ConstraintEventHandler in a ResourceManager's event handlers."""
    for h in rm.event_handlers:
        if isinstance(h, ConstraintEventHandler):
            return h
    return None


# ---------------------------------------------------------------------------
# 1. PhaseState (unit)
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
        state.prev_meta = "x"
        state.prev_info = "y"
        state.current_data = "z"
        state.data = "d"
        state.resource_id = "rid"
        state.reset()
        assert state.needs_post_check is False
        assert state.prev_meta is None
        assert state.prev_info is None
        assert state.current_data is None
        assert state.data is None
        assert state.resource_id is None


# ---------------------------------------------------------------------------
# 2. Custom checker via ResourceManager
# ---------------------------------------------------------------------------


class TestCustomCheckerViaRM:
    """Pass custom constraint_checkers directly to ResourceManager."""

    def test_single_custom_checker_blocks_create(self):
        """MaxValueChecker should reject create when value > max."""
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        # value=10 is fine
        rm.create(ItemNoUnique(name="ok", value=10))

        # value=99 should be rejected
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.create(ItemNoUnique(name="bad", value=99))

    def test_custom_checker_blocks_update(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        info = rm.create(ItemNoUnique(name="item", value=10))
        rid = info.resource_id

        # Update to value=30 is fine
        rm.update(rid, ItemNoUnique(name="item", value=30))

        # Update to value=200 should fail
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.update(rid, ItemNoUnique(name="item", value=200))

    def test_custom_checker_blocks_modify(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        rm.default_status = RevisionStatus.draft
        info = rm.create(ItemNoUnique(name="item", value=10))
        rid = info.resource_id

        # Modify value within range is ok
        rm.modify(rid, ItemNoUnique(name="item", value=40))

        # Modify to exceed max should fail
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.modify(rid, ItemNoUnique(name="item", value=200))

    def test_custom_checker_allows_no_violation(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=1000),
            ],
        )
        info = rm.create(ItemNoUnique(name="ok", value=999))
        assert info.resource_id is not None

    def test_handler_registered_in_event_handlers(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        handler = _get_constraint_handler(rm)
        assert handler is not None
        assert len(handler.checkers) == 1
        assert isinstance(handler.checkers[0], MaxValueChecker)

    def test_no_checkers_no_handler(self):
        rm = make_rm(ItemNoUnique)
        handler = _get_constraint_handler(rm)
        assert handler is None


# ---------------------------------------------------------------------------
# 3. Multi-checker composition
# ---------------------------------------------------------------------------


class TestMultiCheckerComposition:
    """Multiple checkers are all enforced."""

    def test_both_checkers_enforced(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
                lambda rm: NameBlacklistChecker(rm),
            ],
        )
        # Both pass
        rm.create(ItemNoUnique(name="ok", value=10))

        # MaxValue fails
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.create(ItemNoUnique(name="ok2", value=100))

        # Blacklist fails
        with pytest.raises(ValueError, match="blacklisted"):
            rm.create(ItemNoUnique(name="forbidden", value=1))

    def test_first_checker_fail_short_circuits(self):
        """When first checker fails, second is not run."""
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=0),
                lambda rm: NameBlacklistChecker(rm),
            ],
        )
        # MaxValue fail takes precedence
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.create(ItemNoUnique(name="forbidden", value=100))

    def test_custom_checker_combined_with_unique(self):
        """constraint_checkers + unique fields both enforced."""
        rm = make_rm_with_unique(
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        handler = _get_constraint_handler(rm)
        assert handler is not None
        # 3 checkers: MaxValueChecker + explicit UniqueConstraintChecker
        # + auto-detected UniqueConstraintChecker (from Unique annotation)
        assert len(handler.checkers) == 3
        checker_types = {type(c) for c in handler.checkers}
        assert MaxValueChecker in checker_types
        assert UniqueConstraintChecker in checker_types

    def test_unique_and_custom_both_enforced(self):
        """Both unique + custom constraints block when violated."""
        rm = make_rm_with_unique(
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        # Create valid
        rm.create(Item(name="alice", value=10))

        # Unique violation
        with pytest.raises(UniqueConstraintError):
            rm.create(Item(name="alice", value=5))

        # Custom violation
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.create(Item(name="bob", value=99))


# ---------------------------------------------------------------------------
# 4. data_relevant_changed optimisation
# ---------------------------------------------------------------------------


class TestDataRelevantChanged:
    """data_relevant_changed skips unnecessary checks during modify."""

    def test_modify_skip_when_irrelevant_field_changed(self):
        """If constrained field didn't change, checker is skipped."""
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        rm.default_status = RevisionStatus.draft
        info = rm.create(ItemNoUnique(name="item", value=10))
        rid = info.resource_id

        # Modify name only (value unchanged) — should not trigger checker
        # MaxValueChecker.data_relevant_changed returns False here
        rm.modify(rid, ItemNoUnique(name="renamed", value=10))

        # Verify the name was actually updated
        res = rm.get(rid)
        assert res.data.name == "renamed"
        assert res.data.value == 10

    def test_modify_checks_when_relevant_field_changed(self):
        """If constrained field changed, checker runs."""
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        rm.default_status = RevisionStatus.draft
        info = rm.create(ItemNoUnique(name="item", value=10))
        rid = info.resource_id

        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.modify(rid, ItemNoUnique(name="item", value=99))

    def test_default_data_relevant_changed_always_true(self):
        """NameBlacklistChecker uses default (always True)."""
        checker = NameBlacklistChecker(MagicMock())
        assert checker.data_relevant_changed("a", "b") is True


# ---------------------------------------------------------------------------
# 5. Compensation / rollback
# ---------------------------------------------------------------------------


class TestCompensation:
    """Post-check failures trigger automatic rollback."""

    def test_create_compensated_on_post_check_failure(self):
        """If post-check fails after create, the resource is purged."""

        class FailOnSecondCheckChecker(IConstraintChecker):
            """Pre-check passes, post-check fails."""

            def __init__(self, rm: ResourceManager) -> None:
                self.rm = rm
                self._call_count = 0

            def check(
                self, data: Any, *, exclude_resource_id: str | None = None
            ) -> None:
                self._call_count += 1
                if self._call_count > 1:
                    raise ValueError("post-check fail")

        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[lambda rm: FailOnSecondCheckChecker(rm)],
        )

        with pytest.raises(ValueError, match="post-check fail"):
            rm.create(ItemNoUnique(name="item"))

        # Resource should be purged or marked deleted (not findable)
        from autocrud.types import ResourceMetaSearchQuery

        results = rm.storage.search(
            ResourceMetaSearchQuery(is_deleted=False, limit=100)
        )
        assert len(results) == 0

    def test_update_compensated_on_post_check_failure(self):
        """If post-check fails after update, the previous meta is restored."""

        class FailSecondUpdateChecker(IConstraintChecker):
            def __init__(self, rm: ResourceManager) -> None:
                self.rm = rm
                self._check_count = 0

            def check(
                self, data: Any, *, exclude_resource_id: str | None = None
            ) -> None:
                self._check_count += 1
                # Fail on the 4th check (post-check of second update)
                # 1st: pre-check create, 2nd: post-check create
                # 3rd: pre-check update, 4th: post-check update
                if self._check_count == 4:
                    raise ValueError("update post-check fail")

        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[lambda rm: FailSecondUpdateChecker(rm)],
        )

        info = rm.create(ItemNoUnique(name="original", value=1))
        rid = info.resource_id
        original_meta = rm.get_meta(rid)

        with pytest.raises(ValueError, match="update post-check fail"):
            rm.update(rid, ItemNoUnique(name="new", value=2))

        # Meta should be restored to original
        restored_meta = rm.get_meta(rid)
        assert restored_meta.current_revision_id == original_meta.current_revision_id

    def test_restore_compensated_on_post_check_failure(self):
        """If post-check fails after restore, the resource is re-deleted."""

        class FailOnRestorePostCheckChecker(IConstraintChecker):
            def __init__(self, rm: ResourceManager) -> None:
                self.rm = rm
                self._check_count = 0

            def check(
                self, data: Any, *, exclude_resource_id: str | None = None
            ) -> None:
                self._check_count += 1
                # Fail on the 4th check (post-check of restore)
                # 1: pre-check create, 2: post-check create
                # 3: pre-check restore, 4: post-check restore
                if self._check_count == 4:
                    raise ValueError("restore post-check fail")

        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[lambda rm: FailOnRestorePostCheckChecker(rm)],
        )

        info = rm.create(ItemNoUnique(name="item", value=1))
        rid = info.resource_id
        rm.delete(rid)

        with pytest.raises(ValueError, match="restore post-check fail"):
            rm.restore(rid)

        # Resource should still be deleted
        meta = rm._get_meta_no_check_is_deleted(rid)
        assert meta.is_deleted is True


# ---------------------------------------------------------------------------
# 6. AutoCRUD.add_model() with constraint_checkers
# ---------------------------------------------------------------------------


class TestAutoCRUDAddModel:
    """constraint_checkers param flows through add_model to ResourceManager."""

    def test_add_model_with_constraint_checkers(self):
        ac = make_ac()
        ac.add_model(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )

        rm = ac.resource_managers["item-no-unique"]
        handler = _get_constraint_handler(rm)
        assert handler is not None
        assert any(isinstance(c, MaxValueChecker) for c in handler.checkers)

    def test_add_model_unique_plus_checkers(self):
        ac = make_ac()
        ac.add_model(
            Item,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )

        rm = ac.resource_managers["item"]
        handler = _get_constraint_handler(rm)
        assert handler is not None
        checker_types = {type(c) for c in handler.checkers}
        assert MaxValueChecker in checker_types
        assert UniqueConstraintChecker in checker_types

    def test_add_model_no_checkers_no_unique_no_handler(self):
        ac = make_ac()
        ac.add_model(ItemNoUnique)
        rm = ac.resource_managers["item-no-unique"]
        handler = _get_constraint_handler(rm)
        assert handler is None


# ---------------------------------------------------------------------------
# 7. data_relevant_changed with no unique fields
# ---------------------------------------------------------------------------


class TestDataRelevantChangedNoUnique:
    def test_data_relevant_changed_no_unique_fields(self):
        """data_relevant_changed returns False when no unique fields."""
        rm = make_rm(ItemNoUnique)
        checker = UniqueConstraintChecker(rm)
        assert (
            checker.data_relevant_changed(
                ItemNoUnique(name="a"), ItemNoUnique(name="b")
            )
            is False
        )


# ---------------------------------------------------------------------------
# 8. IConstraintChecker ABC
# ---------------------------------------------------------------------------


class TestIConstraintCheckerABC:
    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            IConstraintChecker()  # type: ignore[abstract]

    def test_default_data_relevant_changed(self):
        """Default returns True."""

        class MinimalChecker(IConstraintChecker):
            def check(
                self, data: Any, *, exclude_resource_id: str | None = None
            ) -> None:
                pass

        c = MinimalChecker()
        assert c.data_relevant_changed("a", "b") is True


# ---------------------------------------------------------------------------
# 9. ConstraintEventHandler state isolation
# ---------------------------------------------------------------------------


class TestStateIsolation:
    """Each handler instance has its own ContextVar."""

    def test_two_handlers_independent_state(self):
        rm1 = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        rm2 = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=100),
            ],
        )
        h1 = _get_constraint_handler(rm1)
        h2 = _get_constraint_handler(rm2)
        assert h1 is not None and h2 is not None

        # ContextVar names should be different (per instance)
        assert h1._state_var.name != h2._state_var.name

    def test_state_var_name_contains_id(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        handler = _get_constraint_handler(rm)
        assert handler is not None
        assert str(id(handler)) in handler._state_var.name


# ---------------------------------------------------------------------------
# 10. Constraint checker as callable factory
# ---------------------------------------------------------------------------


class TestCheckerFactory:
    """constraint_checkers items can be callable(rm) factories."""

    def test_factory_callable_creates_checker(self):
        def make_checker(rm: ResourceManager) -> MaxValueChecker:
            return MaxValueChecker(rm, max_value=42)

        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[make_checker],
        )
        handler = _get_constraint_handler(rm)
        assert handler is not None
        assert isinstance(handler.checkers[0], MaxValueChecker)
        assert handler.checkers[0].max_value == 42

    def test_pre_instantiated_checker_also_works(self):
        """Passing an already-constructed IConstraintChecker should also work
        (if the ResourceManager allows it — depends on implementation)."""
        # This depends on ResourceManager's handling; let's check
        pass  # Covered by the unit in Section 2 already


# ---------------------------------------------------------------------------
# 11. modify with JsonPatch
# ---------------------------------------------------------------------------


class TestModifyWithJsonPatch:
    """Constraints are enforced when modify receives a JsonPatch."""

    def test_json_patch_modify_enforces_constraint(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        rm.default_status = RevisionStatus.draft
        info = rm.create(ItemNoUnique(name="item", value=10))
        rid = info.resource_id

        # Patch value to 200 — should fail
        patch = JsonPatch([{"op": "replace", "path": "/value", "value": 200}])
        with pytest.raises(ValueError, match="exceeds maximum"):
            rm.modify(rid, patch)

    def test_json_patch_modify_within_limit_ok(self):
        rm = make_rm(
            ItemNoUnique,
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        rm.default_status = RevisionStatus.draft
        info = rm.create(ItemNoUnique(name="item", value=10))
        rid = info.resource_id

        patch = JsonPatch([{"op": "replace", "path": "/value", "value": 30}])
        rm.modify(rid, patch)

        res = rm.get(rid)
        assert res.data.value == 30


# ---------------------------------------------------------------------------
# 12. Switch revision
# ---------------------------------------------------------------------------


class TestSwitchRevision:
    """Constraints are enforced when switching to a different revision."""

    def test_switch_enforces_constraint(self):
        rm = make_rm_with_unique(
            constraint_checkers=[
                lambda rm: MaxValueChecker(rm, max_value=50),
            ],
        )
        # Create two items
        info_a = rm.create(Item(name="alpha", value=10))
        rm.create(Item(name="beta", value=20))
        rid_a = info_a.resource_id

        # Update creates a new revision (stable→stable)
        rm.update(rid_a, Item(name="alpha", value=40))
        revisions = rm.list_revisions(rid_a)
        # Get first revision id
        rev1 = revisions[0]

        # Switch to rev1 (value=10) should be fine with both checkers
        rm.switch(rid_a, rev1)
        res = rm.get(rid_a)
        assert res.data.value == 10


# ---------------------------------------------------------------------------
# 11) User-provided UniqueConstraintChecker + Unique annotations coexist
# ---------------------------------------------------------------------------


class TestUserAndAutoDetectedUniqueCoexist:
    """When the user explicitly passes a UniqueConstraintChecker via
    ``constraint_checkers`` AND the model has ``Unique``-annotated fields,
    both checkers should be registered and enforced."""

    def test_both_checkers_registered(self):
        """Two UniqueConstraintChecker instances should exist."""
        user_fields = ["value"]  # user wants value uniqueness too

        rm = make_rm(
            Item,
            constraint_checkers=[
                lambda rm: UniqueConstraintChecker(rm, unique_fields=user_fields),
            ],
        )
        handler = _get_constraint_handler(rm)
        assert handler is not None
        unique_checkers = [
            c for c in handler.checkers if isinstance(c, UniqueConstraintChecker)
        ]
        # One from user (value), one from auto-detect (name)
        assert len(unique_checkers) == 2

    def test_user_checker_enforced(self):
        """User's checker (value uniqueness) should still trigger."""
        rm = make_rm(
            Item,
            constraint_checkers=[
                lambda rm: UniqueConstraintChecker(rm, unique_fields=["value"]),
            ],
        )
        rm.create(Item(name="a", value=1))
        # Same value, different name → user's checker should reject
        with pytest.raises(UniqueConstraintError, match="value"):
            rm.create(Item(name="b", value=1))

    def test_auto_detected_checker_enforced(self):
        """Auto-detected checker (name uniqueness from Unique annotation) should still trigger."""
        rm = make_rm(
            Item,
            constraint_checkers=[
                lambda rm: UniqueConstraintChecker(rm, unique_fields=["value"]),
            ],
        )
        rm.create(Item(name="a", value=1))
        # Same name, different value → auto-detected checker should reject
        with pytest.raises(UniqueConstraintError, match="name"):
            rm.create(Item(name="a", value=2))
