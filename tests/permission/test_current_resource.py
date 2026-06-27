#!/usr/bin/env python3
"""Tests for write-phase ``current_resource`` injection (#398, part B).

For write verbs (update / modify / patch / delete) a permission checker can
declare — per action — which slices of the *current* (stored) resource it
reads via :meth:`IPermissionChecker.required_resource_parts`. The
ResourceManager loads only those slices into
``PermissionContext.current_resource`` before running the before-phase check,
so a checker stays a pure function of its context and ``owner_self`` /
embedded-field write ACLs work without each checker doing its own read.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest
from msgspec import UNSET

from specstar.permission.action import ActionBasedPermissionChecker
from specstar.permission.builtins import any_user, owner_self
from specstar.permission.checker import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    ResourcePart,
    requires_resource_parts,
)
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import (
    PermissionDeniedError,
    ResourceAction,
    ResourceIDNotFoundError,
)

NOW = dt.datetime(2026, 1, 1, 12, 0, 0)


@dataclass
class Doc:
    title: str
    level: str = "public"


def make_rm(permission_checker: IPermissionChecker) -> ResourceManager:
    storage = SimpleStorage(
        meta_store=MemoryMetaStore(),
        resource_store=MemoryResourceStore(Doc),  # ty:ignore[invalid-argument-type]
    )
    return ResourceManager(Doc, storage=storage, permission_checker=permission_checker)


def _seed(rm: ResourceManager, user: str = "alice", level: str = "public") -> str:
    with rm.using(user, NOW):
        return rm.create(Doc(title="orig", level=level)).resource_id


# ---------------------------------------------------------------------------
# owner_self now works end-to-end on writes (previously always denied because
# the before-context carried no meta).
# ---------------------------------------------------------------------------


def _owner_checker() -> ActionBasedPermissionChecker:
    # ``read`` (= get/get_meta/...) must be allowed so the internal reads each
    # write performs aren't denied by the cascade.
    return ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.create: any_user,
            ResourceAction.read: any_user,
            ResourceAction.update: owner_self,
            ResourceAction.delete: owner_self,
        }
    )


def test_owner_can_update_own_resource() -> None:
    rm = make_rm(_owner_checker())
    rid = _seed(rm, "alice")
    with rm.using("alice", NOW):
        info = rm.update(rid, Doc(title="new"))
    assert info.resource_id == rid


def test_non_owner_cannot_update() -> None:
    rm = make_rm(_owner_checker())
    rid = _seed(rm, "alice")
    with pytest.raises(PermissionDeniedError):
        with rm.using("bob", NOW):
            rm.update(rid, Doc(title="hijack"))


def test_owner_can_delete_but_other_cannot() -> None:
    rm = make_rm(_owner_checker())
    rid = _seed(rm, "alice")
    with pytest.raises(PermissionDeniedError):
        with rm.using("bob", NOW):
            rm.delete(rid)
    with rm.using("alice", NOW):
        meta = rm.delete(rid)
    assert meta.is_deleted is True


# ---------------------------------------------------------------------------
# Granularity: only the declared slices are loaded.
# ---------------------------------------------------------------------------


class _Recorder(IPermissionChecker):
    """Allows everything; records the ``current_resource`` seen on update."""

    def __init__(self, parts: frozenset[ResourcePart]):
        self._parts = parts
        self.seen: object = "NOT-CALLED"

    def required_resource_parts(
        self, action: ResourceAction
    ) -> frozenset[ResourcePart]:
        return self._parts if action == ResourceAction.update else frozenset()

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        if context.action == ResourceAction.update:
            self.seen = getattr(context, "current_resource", "NO-ATTR")
        return PermissionResult.allow


@pytest.mark.parametrize(
    ("parts", "want_meta", "want_data", "want_info"),
    [
        (frozenset({ResourcePart.META}), True, False, False),
        (frozenset({ResourcePart.DATA}), False, True, False),
        (frozenset({ResourcePart.INFO}), False, False, True),
        (
            frozenset({ResourcePart.META, ResourcePart.DATA, ResourcePart.INFO}),
            True,
            True,
            True,
        ),
    ],
)
def test_only_declared_slices_are_loaded(
    parts: frozenset[ResourcePart],
    want_meta: bool,
    want_data: bool,
    want_info: bool,
) -> None:
    rec = _Recorder(parts)
    rm = make_rm(rec)
    rid = _seed(rm, "alice", level="secret")
    with rm.using("alice", NOW):
        rm.update(rid, Doc(title="new"))

    current = rec.seen
    assert current is not UNSET and current != "NOT-CALLED"
    assert (current.meta is not UNSET) is want_meta
    assert (current.data is not UNSET) is want_data
    assert (current.info is not UNSET) is want_info
    if want_meta:
        assert current.meta.created_by == "alice"
    if want_data:
        assert current.data.level == "secret"


def test_no_declaration_means_no_load() -> None:
    rec = _Recorder(frozenset())
    rm = make_rm(rec)
    rid = _seed(rm, "alice")
    with rm.using("alice", NOW):
        rm.update(rid, Doc(title="new"))
    # current_resource left at its UNSET default — nothing was loaded.
    assert rec.seen is UNSET


# ---------------------------------------------------------------------------
# not-found surfaces before the permission verdict (locked: missing -> 404,
# deny -> 403).
# ---------------------------------------------------------------------------


class _DenyUpdate(IPermissionChecker):
    def required_resource_parts(
        self, action: ResourceAction
    ) -> frozenset[ResourcePart]:
        return frozenset({ResourcePart.META})

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        if context.action == ResourceAction.update:
            return PermissionResult.deny
        return PermissionResult.allow


def test_missing_resource_raises_not_found_before_deny() -> None:
    rm = make_rm(_DenyUpdate())
    # The resource doesn't exist: loading current_resource fails with
    # not-found *before* the deny verdict is reached.
    with pytest.raises(ResourceIDNotFoundError):
        with rm.using("alice", NOW):
            rm.update("does-not-exist", Doc(title="x"))


# ---------------------------------------------------------------------------
# Embedded-field write ACL on the *stored* resource, and old-vs-new compare.
# ---------------------------------------------------------------------------


@requires_resource_parts(ResourcePart.DATA)
def _allow_only_public(context: PermissionContext) -> PermissionResult:
    """Allow the write only if the stored resource is ``level == 'public'``."""
    current = getattr(context, "current_resource", UNSET)
    if current is UNSET or current.data is UNSET:
        return PermissionResult.deny
    return (
        PermissionResult.allow
        if current.data.level == "public"
        else PermissionResult.deny
    )


def _embedded_checker() -> ActionBasedPermissionChecker:
    return ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.create: any_user,
            ResourceAction.read: any_user,
            ResourceAction.update: _allow_only_public,
        }
    )


def test_embedded_field_acl_uses_stored_data() -> None:
    rm = make_rm(_embedded_checker())
    public_id = _seed(rm, "alice", level="public")
    private_id = _seed(rm, "alice", level="private")

    with rm.using("alice", NOW):
        rm.update(public_id, Doc(title="edited", level="public"))

    with pytest.raises(PermissionDeniedError):
        with rm.using("alice", NOW):
            rm.update(private_id, Doc(title="edited", level="private"))


@requires_resource_parts(ResourcePart.DATA)
def _level_is_immutable(context: PermissionContext) -> PermissionResult:
    """Incoming ``data`` (new) vs ``current_resource.data`` (stored) — reject a
    write that changes the immutable ``level`` field."""
    current = getattr(context, "current_resource", UNSET)
    incoming = getattr(context, "data", UNSET)
    if current is UNSET or current.data is UNSET or incoming is UNSET:
        return PermissionResult.deny
    return (
        PermissionResult.allow
        if incoming.level == current.data.level
        else PermissionResult.deny
    )


def test_incoming_vs_stored_data_compare() -> None:
    rm = make_rm(
        ActionBasedPermissionChecker.from_dict(
            {
                ResourceAction.create: any_user,
                ResourceAction.read: any_user,
                ResourceAction.update: _level_is_immutable,
            }
        )
    )
    rid = _seed(rm, "alice", level="public")
    # same level → allowed
    with rm.using("alice", NOW):
        rm.update(rid, Doc(title="t", level="public"))
    # changing level → denied
    with pytest.raises(PermissionDeniedError):
        with rm.using("alice", NOW):
            rm.update(rid, Doc(title="t", level="private"))


# ---------------------------------------------------------------------------
# Aggregation across composite-shaped checkers.
# ---------------------------------------------------------------------------


def test_action_based_aggregates_markers_per_action() -> None:
    chk = ActionBasedPermissionChecker.from_dict(
        {
            ResourceAction.update: owner_self,  # marks META
            ResourceAction.delete: any_user,  # no marker
        }
    )
    assert chk.required_resource_parts(ResourceAction.update) == frozenset(
        {ResourcePart.META}
    )
    assert chk.required_resource_parts(ResourceAction.delete) == frozenset()
