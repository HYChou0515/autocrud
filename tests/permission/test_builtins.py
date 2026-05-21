"""Tests for the built-in permission CheckFunc vocabulary.

These 5 names + `custom:<dotted>` escape are what STEP 1's
``### Permissions`` normalization narrows down to, so each one must
exist as a callable with the ``CheckFunc`` signature.
"""

from __future__ import annotations

from unittest.mock import Mock

from specstar.permission.builtins import (
    admin_only,
    any_authenticated,
    any_user,
    deny_all,
    owner_self,
)
from specstar.permission.checker import DEFAULT_ROOT_USER, PermissionResult


def test_any_authenticated_allows_non_empty_user() -> None:
    # Tracer: user is logged in → allow.
    ctx = Mock(user="alice")
    assert any_authenticated(ctx) is PermissionResult.allow


def test_any_authenticated_denies_anonymous() -> None:
    # Bare-string anonymous (the DependencyProvider default) ≠ logged in.
    ctx = Mock(user="anonymous")
    assert any_authenticated(ctx) is PermissionResult.deny


def test_any_user_allows_anonymous_too() -> None:
    # "public" / "any_user" is the broadest token — even anonymous is OK.
    ctx = Mock(user="anonymous")
    assert any_user(ctx) is PermissionResult.allow


def test_admin_only_allows_root_user() -> None:
    # admin_only matches the configured DEFAULT_ROOT_USER ("root"). A
    # different choice can be wired via spec.configure(admin=...) at
    # the project level.
    ctx = Mock(user=DEFAULT_ROOT_USER)
    assert admin_only(ctx) is PermissionResult.allow


def test_admin_only_denies_others() -> None:
    ctx = Mock(user="alice")
    assert admin_only(ctx) is PermissionResult.deny


def test_deny_all_rejects_everyone() -> None:
    # ``deny_all`` is the "no one can do this action" token. Useful for
    # immutable actions like permanently_delete on certain resources.
    ctx = Mock(user=DEFAULT_ROOT_USER)
    assert deny_all(ctx) is PermissionResult.deny


def test_owner_self_allows_when_user_matches_created_by() -> None:
    # owner_self matches against the canonical ``meta.created_by``
    # field that ResourceManager writes on create.
    ctx = Mock(user="alice", meta=Mock(created_by="alice"))
    assert owner_self(ctx) is PermissionResult.allow


def test_owner_self_denies_when_user_differs() -> None:
    ctx = Mock(user="bob", meta=Mock(created_by="alice"))
    assert owner_self(ctx) is PermissionResult.deny
