"""
ConstraintEventHandler — generic constraint enforcement via event lifecycle.

Provides the **two-phase check + compensate** pattern for any number of
:class:`~autocrud.types.IConstraintChecker` implementations.  Users only
implement ``check()``; this handler manages the entire before → on_success
flow and performs automatic rollback (compensation) on post-check failure.

The built-in :class:`~autocrud.resource_manager.unique_handler.UniqueConstraintChecker`
is the canonical usage example.
"""

from __future__ import annotations

import io
from contextlib import suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Sequence

from jsonpatch import JsonPatch
from msgspec import UNSET

from autocrud.types import (
    EventContext,
    EventContextProto,
    HasData,
    HasDataAndResourceId,
    HasInfo,
    HasResourceId,
    HasRevisionId,
    IConstraintChecker,
    IEventHandler,
    ResourceAction,
    ResourceMeta,
    RevisionInfo,
)

if TYPE_CHECKING:
    from autocrud.resource_manager.core import ResourceManager


# ---------------------------------------------------------------------------
# Per-context state passed between *before* → *on_success*
# ---------------------------------------------------------------------------


class _PhaseState:
    """Mutable bag stored in a :class:`~contextvars.ContextVar`."""

    __slots__ = (
        "needs_post_check",
        "prev_meta",
        "prev_info",
        "current_data",
        "data",
        "resource_id",
    )

    needs_post_check: bool
    prev_meta: ResourceMeta | None
    prev_info: RevisionInfo | None
    current_data: Any
    data: Any
    resource_id: str | None

    def __init__(self) -> None:
        self.needs_post_check = False
        self.prev_meta = None
        self.prev_info = None
        self.current_data = None
        self.data = None
        self.resource_id = None

    def reset(self) -> None:
        self.needs_post_check = False
        self.prev_meta = None
        self.prev_info = None
        self.current_data = None
        self.data = None
        self.resource_id = None


# ---------------------------------------------------------------------------
# Supported (action, phase) pairs
# ---------------------------------------------------------------------------

_SUPPORTED_ACTIONS: frozenset[ResourceAction] = frozenset(
    {
        ResourceAction.create,
        ResourceAction.update,
        ResourceAction.modify,
        ResourceAction.switch,
        ResourceAction.restore,
    }
)

_SUPPORTED_PHASES: frozenset[str] = frozenset({"before", "on_success"})


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class ConstraintEventHandler(IEventHandler):
    """Generic constraint enforcement handler.

    Runs all registered :class:`IConstraintChecker` instances in the
    *before* phase (pre-check) and again in *on_success* (post-check to
    guard against race conditions).  If the post-check fails the handler
    compensates (rolls back) the write automatically.

    Args:
        rm: The owning :class:`ResourceManager`.
        checkers: One or more constraint checkers to enforce.
    """

    def __init__(
        self,
        rm: ResourceManager,
        checkers: Sequence[IConstraintChecker],
    ) -> None:
        self.rm: ResourceManager = rm
        self.checkers: list[IConstraintChecker] = list(checkers)
        self._state_var: ContextVar[_PhaseState] = ContextVar(
            f"_constraint_state_{id(self)}"
        )

    # -- helpers -------------------------------------------------------------

    def _get_state(self) -> _PhaseState:
        try:
            return self._state_var.get()
        except LookupError:
            state = _PhaseState()
            self._state_var.set(state)
            return state

    def _run_checks(self, data: Any, *, exclude_resource_id: str | None = None) -> None:
        """Run all checkers; first failure wins."""
        for checker in self.checkers:
            checker.check(data, exclude_resource_id=exclude_resource_id)

    # -- IEventHandler -------------------------------------------------------

    def is_supported(self, context: EventContext) -> bool:
        if not self.checkers:
            return False
        if not isinstance(context, EventContextProto):
            return False
        with suppress(AttributeError):
            return (
                context.action in _SUPPORTED_ACTIONS
                and context.phase in _SUPPORTED_PHASES
            )
        return False

    def handle_event(self, context: EventContext) -> None:
        if not isinstance(context, EventContextProto):
            return
        if context.phase == "before":
            self._on_before(context)
        elif context.phase == "on_success":
            self._on_success(context)

    # ======================================================================
    # Before phase (pre-check)
    # ======================================================================

    def _on_before(self, context: EventContextProto) -> None:
        state = self._get_state()
        state.reset()

        action = context.action
        if action == ResourceAction.create:
            self._before_create(context, state)  # type: ignore[arg-type]
        elif action == ResourceAction.update:
            self._before_update(context, state)  # type: ignore[arg-type]
        elif action == ResourceAction.modify:
            self._before_modify(context, state)  # type: ignore[arg-type]
        elif action == ResourceAction.switch:
            self._before_switch(context, state)  # type: ignore[arg-type]
        elif action == ResourceAction.restore:
            self._before_restore(context, state)  # type: ignore[arg-type]

    # -- create --------------------------------------------------------------

    def _before_create(self, ctx: HasData, state: _PhaseState) -> None:
        data = ctx.data
        self._run_checks(data)
        state.needs_post_check = True
        state.data = data

    # -- update --------------------------------------------------------------

    def _before_update(self, ctx: HasDataAndResourceId, state: _PhaseState) -> None:
        data = ctx.data
        resource_id = ctx.resource_id
        self._run_checks(data, exclude_resource_id=resource_id)
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = self.rm.get_meta(resource_id)

    # -- modify --------------------------------------------------------------

    def _before_modify(self, ctx: HasDataAndResourceId, state: _PhaseState) -> None:
        data = ctx.data
        if data is UNSET:
            return

        resource_id = ctx.resource_id

        # JsonPatch: resolve to Struct so checkers can inspect field values
        if isinstance(data, JsonPatch):
            data = self.rm._apply_patch(resource_id, data)

        # Load current data to determine whether relevant fields changed
        prev_meta = self.rm.get_meta(resource_id)
        current_data = self.rm._load_revision_data(
            resource_id, prev_meta.current_revision_id
        )

        # Optimisation: skip if no checker considers the change relevant
        if not any(c.data_relevant_changed(current_data, data) for c in self.checkers):
            return

        self._run_checks(data, exclude_resource_id=resource_id)

        # Save state for post-check & compensation
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = prev_meta
        state.prev_info = self.rm.storage.get_resource_revision_info(
            resource_id, prev_meta.current_revision_id
        )
        state.current_data = current_data

    # -- switch --------------------------------------------------------------

    def _before_switch(self, ctx: HasRevisionId, state: _PhaseState) -> None:
        resource_id = ctx.resource_id
        revision_id = ctx.revision_id
        data = self.rm._load_revision_data(resource_id, revision_id)
        self._run_checks(data, exclude_resource_id=resource_id)
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = self.rm.get_meta(resource_id)

    # -- restore -------------------------------------------------------------

    def _before_restore(self, ctx: HasResourceId, state: _PhaseState) -> None:
        resource_id = ctx.resource_id
        meta = self.rm._get_meta_no_check_is_deleted(resource_id)
        if not meta.is_deleted:
            return
        data = self.rm._load_revision_data(resource_id, meta.current_revision_id)
        self._run_checks(data, exclude_resource_id=resource_id)
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = meta

    # ======================================================================
    # On-success phase (post-check + compensate)
    # ======================================================================

    def _on_success(self, context: EventContextProto) -> None:
        state = self._get_state()
        if not state.needs_post_check:
            return

        action = context.action
        try:
            if action == ResourceAction.create:
                self._post_check_create(context, state)  # type: ignore[arg-type]
            elif action == ResourceAction.update:
                self._post_check_update(state)
            elif action == ResourceAction.modify:
                self._post_check_modify(state)
            elif action == ResourceAction.switch:
                self._post_check_switch(state)
            elif action == ResourceAction.restore:
                self._post_check_restore(state)
        finally:
            state.reset()

    # -- create --------------------------------------------------------------

    def _post_check_create(self, ctx: HasInfo, state: _PhaseState) -> None:
        resource_id: str = ctx.info.resource_id
        try:
            self._run_checks(state.data, exclude_resource_id=resource_id)
        except Exception:
            self._compensate_create(resource_id)
            raise

    # -- update --------------------------------------------------------------

    def _post_check_update(self, state: _PhaseState) -> None:
        try:
            self._run_checks(state.data, exclude_resource_id=state.resource_id)
        except Exception:
            self._compensate_restore_meta(state)
            raise

    # -- modify --------------------------------------------------------------

    def _post_check_modify(self, state: _PhaseState) -> None:
        try:
            self._run_checks(state.data, exclude_resource_id=state.resource_id)
        except Exception:
            self._compensate_restore_revision(state)
            raise

    # -- switch --------------------------------------------------------------

    def _post_check_switch(self, state: _PhaseState) -> None:
        try:
            self._run_checks(state.data, exclude_resource_id=state.resource_id)
        except Exception:
            self._compensate_restore_meta(state)
            raise

    # -- restore -------------------------------------------------------------

    def _post_check_restore(self, state: _PhaseState) -> None:
        try:
            self._run_checks(state.data, exclude_resource_id=state.resource_id)
        except Exception:
            self._compensate_re_delete(state)
            raise

    # ======================================================================
    # Compensation helpers (shared by all constraint checkers)
    # ======================================================================

    def _compensate_create(self, resource_id: str) -> None:
        """Hard-purge a just-created resource."""
        try:
            self.rm.storage.purge_meta(resource_id)
        except (KeyError, NotImplementedError):
            try:
                meta = self.rm._get_meta_no_check_is_deleted(resource_id)
                meta.is_deleted = True
                self.rm.storage.save_meta(meta)
            except Exception:
                pass

    def _compensate_restore_meta(self, state: _PhaseState) -> None:
        """Restore the previous meta snapshot."""
        self.rm.storage.save_meta(state.prev_meta)

    def _compensate_restore_revision(self, state: _PhaseState) -> None:
        """Restore both the previous revision data and meta."""
        self.rm.storage.save_revision(
            state.prev_info,
            io.BytesIO(self.rm.encode(state.current_data)),
        )
        self.rm.storage.save_meta(state.prev_meta)

    def _compensate_re_delete(self, state: _PhaseState) -> None:
        """Re-delete a resource that was just restored."""
        meta = self.rm._get_meta_no_check_is_deleted(state.resource_id)
        meta.is_deleted = True
        self.rm.storage.save_meta(meta)
