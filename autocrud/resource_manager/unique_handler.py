"""
UniqueConstraintEventHandler — centralised unique-constraint enforcement.

Replaces the scattered pre-check / post-check / compensate logic that was
previously duplicated across ``ResourceManager.create``, ``update``,
``modify``, ``switch`` and ``restore``.

The handler is registered as the **last** event handler so that permission
checks (``PermissionEventHandler``) run first.
"""

from __future__ import annotations

import threading
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from jsonpatch import JsonPatch
from msgspec import UNSET

from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    EventContext,
    IEventHandler,
    ResourceAction,
    ResourceMeta,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    RevisionInfo,
    UniqueConstraintError,
)

if TYPE_CHECKING:
    from autocrud.resource_manager.core import ResourceManager


# ---------------------------------------------------------------------------
# Thread-local state passed between *before* → *on_success*
# ---------------------------------------------------------------------------


class _PhaseState:
    """Mutable bag that lives on ``threading.local()``."""

    __slots__ = (
        "needs_post_check",
        "prev_meta",
        "prev_info",
        "current_data",
        "data",
        "resource_id",
    )

    def __init__(self) -> None:
        self.needs_post_check: bool = False
        self.prev_meta: ResourceMeta | None = None
        self.prev_info: RevisionInfo | None = None
        self.current_data: Any = None
        self.data: Any = None
        self.resource_id: str | None = None

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

_SUPPORTED_ACTIONS = frozenset(
    {
        ResourceAction.create,
        ResourceAction.update,
        ResourceAction.modify,
        ResourceAction.switch,
        ResourceAction.restore,
    }
)

_SUPPORTED_PHASES = frozenset({"before", "on_success"})


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


class UniqueConstraintEventHandler(IEventHandler):
    """Enforces unique-field constraints via event lifecycle hooks.

    Performs a **pre-check** in the *before* phase and a **post-check** in
    *on_success* (to catch race conditions).  If a post-check fails the
    handler executes a compensating action to undo the write.
    """

    def __init__(self, rm: "ResourceManager") -> None:
        self.rm = rm
        self._local = threading.local()

    # -- helpers to access thread-local state --------------------------------

    def _get_state(self) -> _PhaseState:
        try:
            return self._local.state
        except AttributeError:
            self._local.state = _PhaseState()
            return self._local.state

    def _reset_state(self) -> None:
        self._get_state().reset()

    # -- IEventHandler -------------------------------------------------------

    def is_supported(self, context: EventContext) -> bool:
        if not self.rm._unique_fields:
            return False
        with suppress(AttributeError):
            return (
                context.action in _SUPPORTED_ACTIONS
                and context.phase in _SUPPORTED_PHASES
            )
        return False

    def handle_event(self, context: EventContext) -> None:
        if context.phase == "before":
            self._on_before(context)
        elif context.phase == "on_success":
            self._on_success(context)

    # ======================================================================
    # Before phase (pre-check)
    # ======================================================================

    def _on_before(self, context: EventContext) -> None:
        state = self._get_state()
        state.reset()

        action = context.action
        if action == ResourceAction.create:
            self._before_create(context, state)
        elif action == ResourceAction.update:
            self._before_update(context, state)
        elif action == ResourceAction.modify:
            self._before_modify(context, state)
        elif action == ResourceAction.switch:
            self._before_switch(context, state)
        elif action == ResourceAction.restore:
            self._before_restore(context, state)

    # -- create --------------------------------------------------------------

    def _before_create(self, ctx: EventContext, state: _PhaseState) -> None:
        data = ctx.data
        self._check_unique_constraints(data)
        # Mark for post-check (always needed for create)
        state.needs_post_check = True
        state.data = data

    # -- update --------------------------------------------------------------

    def _before_update(self, ctx: EventContext, state: _PhaseState) -> None:
        data = ctx.data
        resource_id = ctx.resource_id
        self._check_unique_constraints(data, exclude_resource_id=resource_id)
        # Save prev meta for compensation
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = self.rm.get_meta(resource_id)

    # -- modify --------------------------------------------------------------

    def _before_modify(self, ctx: EventContext, state: _PhaseState) -> None:
        data = ctx.data
        if data is UNSET:
            return  # nothing to check

        resource_id = ctx.resource_id

        # JsonPatch: resolve to Struct so we can compare unique fields
        if isinstance(data, JsonPatch):
            data = self.rm._apply_patch(resource_id, data)

        # Load current data to determine whether unique fields actually changed
        prev_meta = self.rm.get_meta(resource_id)
        current_data = self.rm._load_revision_data(
            resource_id, prev_meta.current_revision_id
        )
        if not self._unique_fields_changed(current_data, data):
            return  # unique fields unchanged — nothing to do

        self._check_unique_constraints(data, exclude_resource_id=resource_id)

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

    def _before_switch(self, ctx: EventContext, state: _PhaseState) -> None:
        resource_id = ctx.resource_id
        revision_id = ctx.revision_id
        # Load target revision data
        data = self.rm._load_revision_data(resource_id, revision_id)
        self._check_unique_constraints(data, exclude_resource_id=resource_id)
        # Save state for post-check & compensation
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = self.rm.get_meta(resource_id)

    # -- restore -------------------------------------------------------------

    def _before_restore(self, ctx: EventContext, state: _PhaseState) -> None:
        resource_id = ctx.resource_id
        meta = self.rm._get_meta_no_check_is_deleted(resource_id)
        if not meta.is_deleted:
            return  # not deleted → restore is a no-op, skip check
        data = self.rm._load_revision_data(resource_id, meta.current_revision_id)
        self._check_unique_constraints(data, exclude_resource_id=resource_id)
        # Save state for post-check & compensation
        state.needs_post_check = True
        state.data = data
        state.resource_id = resource_id
        state.prev_meta = meta

    # ======================================================================
    # On-success phase (post-check + compensate)
    # ======================================================================

    def _on_success(self, context: EventContext) -> None:
        state = self._get_state()
        if not state.needs_post_check:
            return

        action = context.action
        try:
            if action == ResourceAction.create:
                self._post_check_create(context, state)
            elif action == ResourceAction.update:
                self._post_check_update(context, state)
            elif action == ResourceAction.modify:
                self._post_check_modify(context, state)
            elif action == ResourceAction.switch:
                self._post_check_switch(context, state)
            elif action == ResourceAction.restore:
                self._post_check_restore(context, state)
        finally:
            state.reset()

    # -- create --------------------------------------------------------------

    def _post_check_create(self, ctx: EventContext, state: _PhaseState) -> None:
        resource_id = ctx.info.resource_id
        try:
            self._check_unique_constraints(state.data, exclude_resource_id=resource_id)
        except UniqueConstraintError:
            self._hard_purge_resource(resource_id)
            raise

    # -- update --------------------------------------------------------------

    def _post_check_update(self, ctx: EventContext, state: _PhaseState) -> None:
        try:
            self._check_unique_constraints(
                state.data, exclude_resource_id=state.resource_id
            )
        except UniqueConstraintError:
            # Compensate: restore previous meta
            self.rm.storage.save_meta(state.prev_meta)
            raise

    # -- modify --------------------------------------------------------------

    def _post_check_modify(self, ctx: EventContext, state: _PhaseState) -> None:
        try:
            self._check_unique_constraints(
                state.data, exclude_resource_id=state.resource_id
            )
        except UniqueConstraintError:
            # Compensate: restore previous revision data + meta
            import io

            self.rm.storage.save_revision(
                state.prev_info,
                io.BytesIO(self.rm.encode(state.current_data)),
            )
            self.rm.storage.save_meta(state.prev_meta)
            raise

    # -- switch --------------------------------------------------------------

    def _post_check_switch(self, ctx: EventContext, state: _PhaseState) -> None:
        try:
            self._check_unique_constraints(
                state.data, exclude_resource_id=state.resource_id
            )
        except UniqueConstraintError:
            # Compensate: restore previous meta
            self.rm.storage.save_meta(state.prev_meta)
            raise

    # -- restore -------------------------------------------------------------

    def _post_check_restore(self, ctx: EventContext, state: _PhaseState) -> None:
        try:
            self._check_unique_constraints(
                state.data, exclude_resource_id=state.resource_id
            )
        except UniqueConstraintError:
            # Compensate: re-delete the resource
            meta = self.rm._get_meta_no_check_is_deleted(state.resource_id)
            meta.is_deleted = True
            self.rm.storage.save_meta(meta)
            raise

    # ======================================================================
    # Ported helpers (formerly on ResourceManager)
    # ======================================================================

    def _unique_fields_changed(self, current_data: Any, new_data: Any) -> bool:
        """Return True if any unique-constrained field value differs."""
        if not self.rm._unique_fields:
            return False
        current_indexed = self.rm._extract_indexed_values(current_data)
        new_indexed = self.rm._extract_indexed_values(new_data)
        return any(
            new_indexed.get(f) != current_indexed.get(f) for f in self.rm._unique_fields
        )

    def _check_unique_constraints(
        self,
        data: Any,
        *,
        exclude_resource_id: str | None = None,
    ) -> None:
        """Raise ``UniqueConstraintError`` if any unique-annotated field value
        is already used by another (non-deleted) resource.
        """
        if not self.rm._unique_fields:
            return
        indexed = self.rm._extract_indexed_values(data)
        for field_path in self.rm._unique_fields:
            value = indexed.get(field_path)
            if value is None:
                continue
            query = ResourceMetaSearchQuery(
                conditions=[
                    DataSearchCondition(
                        field_path=field_path,
                        operator=DataSearchOperator.equals,
                        value=value,
                    )
                ],
                is_deleted=False,
                limit=1,
                sorts=[
                    ResourceMetaSearchSort(
                        key=ResourceMetaSortKey.updated_time,
                        direction=ResourceMetaSortDirection.ascending,
                    )
                ],
            )
            matches = self.rm.storage.search(query)
            if not matches:
                continue
            first = matches[0]
            if (
                exclude_resource_id is not None
                and first.resource_id == exclude_resource_id
            ):
                continue  # this resource is the earliest owner — no conflict
            raise UniqueConstraintError(field_path, value, first.resource_id)

    def _hard_purge_resource(self, resource_id: str) -> None:
        """Hard-delete a resource's metadata as a unique-constraint rollback."""
        try:
            self.rm.storage.purge_meta(resource_id)
        except (KeyError, NotImplementedError):
            try:
                meta = self.rm._get_meta_no_check_is_deleted(resource_id)
                meta.is_deleted = True
                self.rm.storage.save_meta(meta)
            except Exception:
                pass
