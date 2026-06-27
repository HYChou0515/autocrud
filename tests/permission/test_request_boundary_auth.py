#!/usr/bin/env python3
"""Request-boundary authorization (#402).

A single request-level operation used to run the permission checker once per
*nested* operation it performs internally:

* ``patch`` → internal ``get`` (read current data) + ``update`` (write it back)
* ``get``   → internal ``get_meta`` + ``get_resource_revision``

That meant a checker scoped to ``patch`` was not enough — the caller also had to
be granted ``read`` and ``update``, and every PATCH paid 3 checker invocations.

Authorization is now applied **once, at the outermost operation**: the first
event-emitting op in a call stack runs the permission gate; any nested op skips
*only* its permission check (every other event handler still fires). These tests
pin that contract and its (documented) behavior change.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest

from specstar.events import EventContext, IEventHandler
from specstar.permission.action import ActionBasedPermissionChecker
from specstar.permission.builtins import any_user, owner_self
from specstar.permission.checker import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    ResourcePart,
)
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import (
    MergePatch,
    PermissionDeniedError,
    ResourceAction,
)

NOW = dt.datetime(2026, 1, 1, 12, 0, 0)


@dataclass
class Doc:
    title: str
    level: str = "public"


def make_rm(
    permission_checker: IPermissionChecker,
    event_handlers: list[IEventHandler] | None = None,
) -> ResourceManager:
    storage = SimpleStorage(
        meta_store=MemoryMetaStore(),
        resource_store=MemoryResourceStore(Doc),  # ty:ignore[invalid-argument-type]
    )
    return ResourceManager(
        Doc,
        storage=storage,
        permission_checker=permission_checker,
        event_handlers=event_handlers,
    )


def _seed(rm: ResourceManager, user: str = "alice") -> str:
    with rm.using(user, NOW):
        return rm.create(Doc(title="orig")).resource_id


class _CountingChecker(IPermissionChecker):
    """Allows everything; records the action of every permission check it runs."""

    def __init__(self) -> None:
        self.seen: list[ResourceAction] = []

    def required_resource_parts(
        self, action: ResourceAction
    ) -> frozenset[ResourcePart]:
        return frozenset()

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.seen.append(context.action)
        return PermissionResult.allow


class _BeforeActionRecorder(IEventHandler):
    """A plain (non-permission) event handler that records the action of every
    before-phase context it observes."""

    def __init__(self) -> None:
        self.seen: list[ResourceAction] = []

    def is_supported(self, context: EventContext) -> bool:
        return getattr(context, "phase", None) == "before" and hasattr(
            context, "action"
        )

    def handle_event(self, context: EventContext) -> None:
        self.seen.append(context.action)


# ---------------------------------------------------------------------------
# Authorization happens once, at the outermost op — nested ops are not rechecked.
# ---------------------------------------------------------------------------


def test_patch_checks_permission_once() -> None:
    chk = _CountingChecker()
    rm = make_rm(chk)
    rid = _seed(rm)
    chk.seen.clear()
    with rm.using("alice", NOW):
        rm.patch(rid, MergePatch({"title": "new"}))
    # Only the outermost ``patch`` is checked — not the internal get/update.
    assert chk.seen == [ResourceAction.patch]


def test_get_checks_permission_once() -> None:
    chk = _CountingChecker()
    rm = make_rm(chk)
    rid = _seed(rm)
    chk.seen.clear()
    with rm.using("alice", NOW):
        rm.get(rid)
    # Only the outermost ``get`` is checked — not the nested get_meta /
    # get_resource_revision a single read fans out into.
    assert chk.seen == [ResourceAction.get]


# ---------------------------------------------------------------------------
# Nested ops still fire their *other* event handlers — only the permission
# check is suppressed (this is what separates approach A from "patch uses
# internal non-event read/write").
# ---------------------------------------------------------------------------


def test_nested_events_fire_but_permission_checked_once() -> None:
    perm = _CountingChecker()
    rec = _BeforeActionRecorder()
    rm = make_rm(perm, event_handlers=[rec])
    rid = _seed(rm)
    perm.seen.clear()
    rec.seen.clear()
    with rm.using("alice", NOW):
        rm.patch(rid, MergePatch({"title": "new"}))
    # Permission gate ran once (outermost patch only)...
    assert perm.seen == [ResourceAction.patch]
    # ...but the nested get + update before-events still reached other handlers.
    assert ResourceAction.patch in rec.seen
    assert ResourceAction.get in rec.seen
    assert ResourceAction.update in rec.seen


# ---------------------------------------------------------------------------
# Behavior change (#402): granting only ``patch`` is now sufficient — the
# nested get/update it performs are no longer separately authorized.
# ---------------------------------------------------------------------------


def _only_patch_checker() -> ActionBasedPermissionChecker:
    # No read/update mapping: if the nested ops were still checked, they would be
    # denied (unmapped action -> not_applicable -> deny).
    return ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.create: any_user,
            ResourceAction.patch: any_user,
        }
    )


def test_patch_succeeds_with_only_patch_granted() -> None:
    rm = make_rm(_only_patch_checker())
    rid = _seed(rm)
    with rm.using("alice", NOW):
        info = rm.patch(rid, MergePatch({"title": "patched"}))
    assert info.resource_id == rid


# ---------------------------------------------------------------------------
# No security regression: the outermost op is *always* authorized.
# ---------------------------------------------------------------------------


def _owner_patch_checker() -> ActionBasedPermissionChecker:
    return ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.create: any_user,
            ResourceAction.read: any_user,
            ResourceAction.patch: owner_self,
        }
    )


def test_outermost_patch_still_enforced_for_non_owner() -> None:
    rm = make_rm(_owner_patch_checker())
    rid = _seed(rm, "alice")
    with pytest.raises(PermissionDeniedError):
        with rm.using("bob", NOW):
            rm.patch(rid, MergePatch({"title": "hijack"}))


def test_outermost_patch_allowed_for_owner() -> None:
    rm = make_rm(_owner_patch_checker())
    rid = _seed(rm, "alice")
    with rm.using("alice", NOW):
        info = rm.patch(rid, MergePatch({"title": "ok"}))
    assert info.resource_id == rid
