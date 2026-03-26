"""Tests for the operation context system (using(), explicit kwargs, strict mode)."""

import datetime as dt
import warnings

import pytest
from msgspec import UNSET, Struct

from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import MissingOperationContextError

# ── Test model ──────────────────────────────────────────────────────


class Item(Struct):
    name: str
    value: int = 0


# ── Fixtures ────────────────────────────────────────────────────────

NOW = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
NOW2 = dt.datetime(2025, 6, 15, tzinfo=dt.timezone.utc)
NOW3 = dt.datetime(2025, 12, 31, tzinfo=dt.timezone.utc)


def _make_storage():
    return SimpleStorage(MemoryMetaStore(), MemoryResourceStore())


def make_rm(
    *,
    default_user: str | None = None,
    default_now=None,
    strict: bool = False,
    storage=None,
) -> ResourceManager:
    kwargs = {}
    if default_user is not None:
        kwargs["default_user"] = default_user
    if default_now is not None:
        kwargs["default_now"] = default_now
    return ResourceManager(
        Item,
        storage=storage or _make_storage(),
        strict_operation_context=strict,
        **kwargs,
    )


# ═══════════════════════════════════════════════════════════════════
# using() basic behavior
# ═══════════════════════════════════════════════════════════════════


class TestUsingBasic:
    def test_using_sets_context(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW):
            info = rm.create(Item(name="a"))
        assert info.created_by == "alice"
        assert info.created_time == NOW

    def test_using_nested_override(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW):
            with rm.using(now=NOW2):
                info = rm.create(Item(name="b"))
        assert info.created_by == "alice"
        assert info.created_time == NOW2

    def test_using_as_operator(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW) as op:
            from autocrud.resource_manager.core import ResourceOps

            assert isinstance(op, ResourceOps)
            info = op.create(Item(name="c"))
        assert info.created_by == "alice"

    def test_using_context_cleanup(self):
        rm = make_rm()
        with rm.using(user="alice", now=NOW):
            pass
        # After scope exits, context should be cleaned up.
        # Without defaults, accessing user should raise.
        assert rm.user_or_unset is UNSET
        assert rm.now_or_unset is UNSET


# ═══════════════════════════════════════════════════════════════════
# Explicit kwargs
# ═══════════════════════════════════════════════════════════════════


class TestExplicitKwargs:
    def test_create_with_explicit_user_now(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        assert info.created_by == "bob"
        assert info.created_time == NOW

    def test_create_with_explicit_resource_id(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW, resource_id="my-id")
        assert info.resource_id == "my-id"

    def test_update_with_explicit_user_now(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info.resource_id
        info2 = rm.update(rid, Item(name="b"), user="carol", now=NOW2)
        assert info2.updated_by == "carol"
        assert info2.updated_time == NOW2

    def test_delete_with_explicit_user_now(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info.resource_id
        meta = rm.delete(rid, user="carol", now=NOW2)
        assert meta.is_deleted is True
        assert meta.updated_by == "carol"
        assert meta.updated_time == NOW2

    def test_switch_with_explicit_user_now(self):
        rm = make_rm()
        info1 = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info1.resource_id
        info2 = rm.update(rid, Item(name="b"), user="bob", now=NOW)
        # Switch back to revision 1
        meta = rm.switch(rid, info1.revision_id, user="carol", now=NOW2)
        assert meta.updated_by == "carol"
        assert meta.updated_time == NOW2

    def test_restore_with_explicit_user_now(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info.resource_id
        rm.delete(rid, user="bob", now=NOW)
        meta = rm.restore(rid, user="carol", now=NOW2)
        assert meta.is_deleted is False
        assert meta.updated_by == "carol"
        assert meta.updated_time == NOW2

    def test_patch_with_explicit_user_now(self):
        rm = make_rm()
        from jsonpatch import JsonPatch

        info = rm.create(Item(name="a", value=1), user="bob", now=NOW)
        rid = info.resource_id
        patch = JsonPatch([{"op": "replace", "path": "/value", "value": 42}])
        info2 = rm.patch(rid, patch, user="carol", now=NOW2)
        assert info2.updated_by == "carol"

    def test_modify_with_explicit_user_now(self):
        from autocrud.types import RevisionStatus

        rm = make_rm()
        info = rm.create(
            Item(name="a"),
            user="bob",
            now=NOW,
            status=RevisionStatus.draft,
        )
        rid = info.resource_id
        info2 = rm.modify(rid, Item(name="b"), user="carol", now=NOW2)
        assert info2.updated_by == "carol"

    def test_create_or_update_with_explicit_user_now(self):
        rm = make_rm()
        # First call creates
        info = rm.create_or_update("rid-1", Item(name="a"), user="bob", now=NOW)
        assert info.created_by == "bob"
        # Second call updates
        info2 = rm.create_or_update("rid-1", Item(name="b"), user="carol", now=NOW2)
        assert info2.updated_by == "carol"


# ═══════════════════════════════════════════════════════════════════
# Resolution order: kwargs > scope > defaults
# ═══════════════════════════════════════════════════════════════════


class TestResolutionOrder:
    def test_kwargs_override_scope(self):
        rm = make_rm()
        with rm.using(user="bob", now=NOW):
            info = rm.create(Item(name="a"), user="alice")
        assert info.created_by == "alice"
        # now should come from scope
        assert info.created_time == NOW

    def test_scope_override_defaults(self):
        rm = make_rm(default_user="default-user", default_now=lambda: NOW)
        with rm.using(user="scope-user"):
            info = rm.create(Item(name="a"))
        assert info.created_by == "scope-user"
        # now from defaults
        assert info.created_time == NOW

    def test_kwargs_override_defaults(self):
        rm = make_rm(default_user="default-user", default_now=lambda: NOW)
        info = rm.create(Item(name="a"), user="kwarg-user", now=NOW2)
        assert info.created_by == "kwarg-user"
        assert info.created_time == NOW2

    def test_full_resolution_chain(self):
        """kwargs > scope > defaults — all three layers."""
        rm = make_rm(default_user="default-user", default_now=lambda: NOW3)
        with rm.using(user="scope-user", now=NOW):
            # user from kwargs, now from scope (overrides default)
            info = rm.create(Item(name="a"), user="kwarg-user")
        assert info.created_by == "kwarg-user"
        assert info.created_time == NOW


# ═══════════════════════════════════════════════════════════════════
# Strict mode
# ═══════════════════════════════════════════════════════════════════


class TestStrictMode:
    def test_strict_create_without_context_raises(self):
        rm = make_rm(strict=True)
        with pytest.raises(MissingOperationContextError) as exc_info:
            rm.create(Item(name="a"))
        assert "user" in exc_info.value.missing_fields
        assert "now" in exc_info.value.missing_fields

    def test_strict_with_defaults_passes(self):
        rm = make_rm(default_user="system", default_now=lambda: NOW, strict=True)
        info = rm.create(Item(name="a"))
        assert info.created_by == "system"

    def test_strict_with_kwargs_passes(self):
        rm = make_rm(strict=True)
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        assert info.created_by == "bob"

    def test_strict_with_scope_passes(self):
        rm = make_rm(strict=True)
        with rm.using(user="alice", now=NOW):
            info = rm.create(Item(name="a"))
        assert info.created_by == "alice"

    def test_strict_partial_context_raises(self):
        rm = make_rm(strict=True)
        with pytest.raises(MissingOperationContextError) as exc_info:
            rm.create(Item(name="a"), user="bob")
        assert exc_info.value.missing_fields == ["now"]

    def test_non_strict_missing_context_no_error(self):
        """Non-strict mode: missing context causes LookupError from ContextVar,
        not MissingOperationContextError."""
        rm = make_rm(strict=False)
        with pytest.raises(LookupError):
            rm.create(Item(name="a"))

    def test_strict_update_without_context_raises(self):
        storage = _make_storage()
        rm = make_rm(
            strict=True, default_user="sys", default_now=lambda: NOW, storage=storage
        )
        info = rm.create(Item(name="a"))
        rid = info.resource_id
        # Now make a strict RM without defaults
        rm2 = ResourceManager(
            Item,
            storage=storage,
            strict_operation_context=True,
        )
        with pytest.raises(MissingOperationContextError):
            rm2.update(rid, Item(name="b"))

    def test_strict_delete_without_context_raises(self):
        storage = _make_storage()
        rm = make_rm(
            strict=True, default_user="sys", default_now=lambda: NOW, storage=storage
        )
        info = rm.create(Item(name="a"))
        rid = info.resource_id
        rm2 = ResourceManager(
            Item,
            storage=storage,
            strict_operation_context=True,
        )
        with pytest.raises(MissingOperationContextError):
            rm2.delete(rid)


# ═══════════════════════════════════════════════════════════════════
# meta_provide deprecation
# ═══════════════════════════════════════════════════════════════════


class TestMetaProvideDeprecation:
    def test_meta_provide_emits_deprecation_warning(self):
        rm = make_rm()
        with pytest.warns(DeprecationWarning, match="meta_provide.*deprecated"):
            with rm.meta_provide(user="alice", now=NOW):
                pass

    def test_meta_provide_still_works(self):
        rm = make_rm()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with rm.meta_provide(user="alice", now=NOW):
                info = rm.create(Item(name="a"))
        assert info.created_by == "alice"
        assert info.created_time == NOW


# ═══════════════════════════════════════════════════════════════════
# MissingOperationContextError
# ═══════════════════════════════════════════════════════════════════


class TestMissingOperationContextError:
    def test_error_message_includes_missing_fields(self):
        err = MissingOperationContextError(["user", "now"])
        assert "user" in str(err)
        assert "now" in str(err)
        assert err.missing_fields == ["user", "now"]

    def test_error_message_includes_method_hint(self):
        err = MissingOperationContextError(["user"], method_name="create")
        assert "create" in str(err)
        assert err.method_name == "create"

    def test_error_without_method_name(self):
        err = MissingOperationContextError(["now"])
        assert "now" in str(err)
        assert err.method_name is None


# ═══════════════════════════════════════════════════════════════════
# Read methods don't need context
# ═══════════════════════════════════════════════════════════════════


class TestReadMethodsNoContext:
    def test_get_without_context(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info.resource_id
        # Get should work without any context
        resource = rm.get(rid)
        assert resource.data.name == "a"

    def test_search_without_context(self):
        from autocrud.types import ResourceMetaSearchQuery

        rm = make_rm()
        rm.create(Item(name="a"), user="bob", now=NOW)
        results = rm.search_resources(ResourceMetaSearchQuery())
        assert len(results) >= 1

    def test_exists_without_context(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        assert rm.exists(info.resource_id) is True
        assert rm.exists("nonexistent") is False

    def test_count_without_context(self):
        from autocrud.types import ResourceMetaSearchQuery

        rm = make_rm()
        rm.create(Item(name="a"), user="bob", now=NOW)
        assert rm.count_resources(ResourceMetaSearchQuery()) >= 1


# ── AutoCRUD-level strict_operation_context ─────────────────────────


class TestAutoCRUDStrictOperationContext:
    """strict_operation_context should be set at AutoCRUD level and
    propagated to all ResourceManagers created via add_model()."""

    def test_configure_strict_propagates_to_rm(self):
        from autocrud import AutoCRUD

        crud = AutoCRUD(
            strict_operation_context=True,
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Item)
        rm = crud.get_resource_manager(Item)
        assert rm.strict_operation_context is True

    def test_default_is_not_strict(self):
        from autocrud import AutoCRUD

        crud = AutoCRUD(default_user="admin", default_now=dt.datetime.now)
        crud.add_model(Item)
        rm = crud.get_resource_manager(Item)
        assert rm.strict_operation_context is False

    def test_configure_after_init(self):
        from autocrud import AutoCRUD

        crud = AutoCRUD()
        crud.configure(
            strict_operation_context=True,
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Item)
        rm = crud.get_resource_manager(Item)
        assert rm.strict_operation_context is True

    def test_strict_autocrud_create_without_context_raises(self):
        from autocrud import AutoCRUD

        crud = AutoCRUD(strict_operation_context=True)
        crud.add_model(Item)
        rm = crud.get_resource_manager(Item)
        with pytest.raises(MissingOperationContextError):
            rm.create(Item(name="a"))

    def test_strict_autocrud_create_with_defaults_passes(self):
        from autocrud import AutoCRUD

        crud = AutoCRUD(
            strict_operation_context=True,
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Item)
        rm = crud.get_resource_manager(Item)
        info = rm.create(Item(name="a"))
        assert info.resource_id is not None


# ═══════════════════════════════════════════════════════════════════
# permanently_delete with operation context
# ═══════════════════════════════════════════════════════════════════


class TestPermanentlyDeleteContext:
    """permanently_delete should support user/now kwargs and context_aware."""

    def test_permanently_delete_with_explicit_user_now(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info.resource_id
        meta = rm.permanently_delete(rid, user="carol", now=NOW2)
        assert meta.resource_id == rid

    def test_permanently_delete_with_using_scope(self):
        rm = make_rm()
        info = rm.create(Item(name="a"), user="bob", now=NOW)
        rid = info.resource_id
        with rm.using(user="carol", now=NOW2):
            meta = rm.permanently_delete(rid)
        assert meta.resource_id == rid

    def test_strict_permanently_delete_without_context_raises(self):
        storage = _make_storage()
        rm = make_rm(
            strict=True, default_user="sys", default_now=lambda: NOW, storage=storage
        )
        info = rm.create(Item(name="a"))
        rid = info.resource_id
        rm2 = ResourceManager(
            Item,
            storage=storage,
            strict_operation_context=True,
        )
        with pytest.raises(MissingOperationContextError):
            rm2.permanently_delete(rid)

    def test_strict_permanently_delete_with_kwargs_passes(self):
        storage = _make_storage()
        rm = make_rm(
            strict=True, default_user="sys", default_now=lambda: NOW, storage=storage
        )
        info = rm.create(Item(name="a"))
        rid = info.resource_id
        rm2 = ResourceManager(
            Item,
            storage=storage,
            strict_operation_context=True,
        )
        meta = rm2.permanently_delete(rid, user="admin", now=NOW2)
        assert meta.resource_id == rid

    def test_strict_permanently_delete_with_scope_passes(self):
        storage = _make_storage()
        rm = make_rm(
            strict=True, default_user="sys", default_now=lambda: NOW, storage=storage
        )
        info = rm.create(Item(name="a"))
        rid = info.resource_id
        rm2 = ResourceManager(
            Item,
            storage=storage,
            strict_operation_context=True,
        )
        with rm2.using(user="admin", now=NOW2):
            meta = rm2.permanently_delete(rid)
        assert meta.resource_id == rid


# ═══════════════════════════════════════════════════════════════════
# Strict mode + meta_provide (legacy) combination
# ═══════════════════════════════════════════════════════════════════


class TestStrictModeWithMetaProvide:
    """Strict mode should still work when context comes from meta_provide."""

    def test_strict_with_meta_provide_passes(self):
        rm = make_rm(strict=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with rm.meta_provide(user="alice", now=NOW):
                info = rm.create(Item(name="a"))
        assert info.created_by == "alice"

    def test_strict_with_meta_provide_partial_raises(self):
        rm = make_rm(strict=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            with rm.meta_provide(user="alice"):
                with pytest.raises(MissingOperationContextError) as exc_info:
                    rm.create(Item(name="a"))
                assert exc_info.value.missing_fields == ["now"]

    def test_meta_provide_still_warns_in_strict_mode(self):
        rm = make_rm(strict=True)
        with pytest.warns(DeprecationWarning, match="meta_provide.*deprecated"):
            with rm.meta_provide(user="alice", now=NOW):
                rm.create(Item(name="a"))


# ═══════════════════════════════════════════════════════════════════
# Route templates use using() instead of meta_provide()
# ═══════════════════════════════════════════════════════════════════


class TestRouteTemplatesUseUsing:
    """Route templates should use using() not meta_provide()."""

    def test_create_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.create import CreateRouteTemplate

        src = inspect.getsource(CreateRouteTemplate)
        assert "meta_provide" not in src
        assert "using(" in src or ".using(" in src

    def test_delete_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.delete import (
            BatchDeleteRouteTemplate,
            BatchRestoreRouteTemplate,
            DeleteRouteTemplate,
            PermanentlyDeleteRouteTemplate,
            RestoreRouteTemplate,
        )

        for cls in [
            DeleteRouteTemplate,
            PermanentlyDeleteRouteTemplate,
            BatchDeleteRouteTemplate,
            BatchRestoreRouteTemplate,
            RestoreRouteTemplate,
        ]:
            src = inspect.getsource(cls)
            assert "meta_provide" not in src, f"{cls.__name__} still uses meta_provide"

    def test_update_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.update import UpdateRouteTemplate

        src = inspect.getsource(UpdateRouteTemplate)
        assert "meta_provide" not in src

    def test_get_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.get import ReadRouteTemplate

        src = inspect.getsource(ReadRouteTemplate)
        assert "meta_provide" not in src

    def test_patch_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.patch import PatchRouteTemplate

        src = inspect.getsource(PatchRouteTemplate)
        assert "meta_provide" not in src

    def test_switch_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.switch import SwitchRevisionRouteTemplate

        src = inspect.getsource(SwitchRevisionRouteTemplate)
        assert "meta_provide" not in src

    def test_migrate_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.migrate import MigrateRouteTemplate

        src = inspect.getsource(MigrateRouteTemplate)
        assert "meta_provide" not in src

    def test_rerun_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.rerun import RerunRouteTemplate

        src = inspect.getsource(RerunRouteTemplate)
        assert "meta_provide" not in src

    def test_job_logs_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.job_logs import JobLogsRouteTemplate

        src = inspect.getsource(JobLogsRouteTemplate)
        assert "meta_provide" not in src

    def test_graphql_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate

        src = inspect.getsource(GraphQLRouteTemplate)
        assert "meta_provide" not in src

    def test_search_route_uses_using(self):
        import inspect

        from autocrud.crud.route_templates.search import ListRouteTemplate

        src = inspect.getsource(ListRouteTemplate)
        assert "meta_provide" not in src


# ═══════════════════════════════════════════════════════════════════
# Message queue uses using() instead of meta_provide()
# ═══════════════════════════════════════════════════════════════════


class TestMessageQueueUsesUsing:
    """Message queue internal helper should use using() instead of meta_provide()."""

    def test_rm_using_helper_uses_using(self):
        import inspect

        from autocrud.message_queue.basic import BasicMessageQueue

        src = inspect.getsource(BasicMessageQueue._rm_using)
        assert "meta_provide" not in src
        assert "using(" in src or ".using(" in src


# ═══════════════════════════════════════════════════════════════════
# Permission internals use using() instead of meta_provide()
# ═══════════════════════════════════════════════════════════════════


class TestPermissionUsesUsing:
    """Permission handlers should use using() instead of meta_provide()."""

    def test_acl_uses_using(self):
        import inspect

        from autocrud.permission.acl import ACLPermissionChecker

        src = inspect.getsource(ACLPermissionChecker)
        assert "meta_provide" not in src

    def test_rbac_uses_using(self):
        import inspect

        from autocrud.permission.rbac import RBACPermissionChecker

        src = inspect.getsource(RBACPermissionChecker)
        assert "meta_provide" not in src
