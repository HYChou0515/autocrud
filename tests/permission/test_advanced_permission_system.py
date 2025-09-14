"""測試新的權限檢查系統"""

import datetime as dt
from contextlib import suppress

import pytest
from msgspec import Struct

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from autocrud.permission.action import ActionBasedPermissionChecker
from autocrud.types import (
    PermissionResult,
)
from autocrud.permission.composite import CompositePermissionChecker
from autocrud.permission.rbac import (
    RBACPermissionChecker,
    RBACPermissionEntry,
    RoleMembership,
)
from autocrud.types import (
    IPermissionChecker,
    PermissionContext,
    ResourceIDNotFoundError,
)
from autocrud.resource_manager.core import (
    PermissionEventHandler,
    ResourceManager,
    SimpleStorage,
)
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import PermissionDeniedError, ResourceAction


class DataStruct(Struct):
    name: str = "default"
    sensitive_field: str | None = None


class DataStruct2(Struct):
    title: str = "default"


class DoNothingPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        return PermissionResult.not_applicable


class RejectingPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        return PermissionResult.deny


class AcceptingPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        return PermissionResult.allow


class MockPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)

        # 簡單的測試邏輯
        if context.user == "blocked_user":
            return PermissionResult.deny

        return PermissionResult.allow


class TestAdvancedPermissionChecking:
    """測試進階權限檢查系統"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=MemoryResourceStore(DataStruct),
        )

        permission_checker = ACLPermissionChecker(
            policy=Policy.default_allow | Policy.deny_overrides,
        )
        self.pm = permission_checker.resource_manager

        resource_manager = ResourceManager(
            DataStruct,
            storage=storage,
            permission_checker=permission_checker,
        )
        self.resource_manager = resource_manager
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=MemoryResourceStore(dict),
        )

    def test_default_permission_checker(self):
        """測試預設權限檢查器"""
        # 設定權限管理器到 resource_manager
        # 建立權限規則
        with self.pm.meta_provide("root", dt.datetime.now()):
            acl = ACLPermission(
                subject="alice",
                object="data_struct",
                action=ResourceAction.get_meta,
                effect=PermissionResult.allow,
            )
            self.pm.create(acl)

        # 測試權限檢查
        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            # 這應該會成功，因為有權限
            try:
                meta = self.resource_manager.get_meta("test:123")
            except Exception as e:
                # 只要不是 PermissionDeniedError 就算通過權限檢查

                assert not isinstance(e, PermissionDeniedError), (
                    f"權限檢查應該通過，但得到權限錯誤: {e}"
                )

    def test_custom_permission_checker(self):
        """測試自定義權限檢查器"""
        checker = MockPermissionChecker()
        self.resource_manager.event_handlers.append(PermissionEventHandler(checker))

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            try:
                self.resource_manager.get_meta("test:123")
            except Exception:
                pass  # 忽略資源不存在的錯誤，我們只關心權限檢查

        # 檢查權限檢查器是否被呼叫
        assert len(checker.check_calls) == 1
        context = checker.check_calls[0]
        assert context.user == "alice"
        assert context.action == ResourceAction.get_meta  # 現在是 ResourceAction enum
        assert context.resource_name == "data_struct"

    def test_custom_permission_checker_2(self):
        """測試自定義權限檢查器"""
        checker = ActionBasedPermissionChecker.from_dict(
            {
                "read": lambda _: PermissionResult.deny,
                "create": lambda _: PermissionResult.allow,
            },
        )
        self.resource_manager.event_handlers.append(PermissionEventHandler(checker))

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.resource_manager.get_meta("test:123")

    def test_permission_denied(self):
        """測試權限拒絕"""
        checker = MockPermissionChecker()
        self.resource_manager.event_handlers.append(PermissionEventHandler(checker))

        with self.resource_manager.meta_provide("blocked_user", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.resource_manager.get_meta("test:123")

    def test_composite_permission_checker(self):
        """測試組合權限檢查器"""
        # 創建兩個檢查器
        checker1 = MockPermissionChecker()
        checker2 = MockPermissionChecker()

        # 創建組合檢查器
        composite = CompositePermissionChecker([checker1, checker2])

        self.resource_manager.event_handlers.append(PermissionEventHandler(composite))

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            with suppress(ResourceIDNotFoundError):
                self.resource_manager.get_meta("test:123")

        # 只有第一個檢查器應該被呼叫（因為它返回了 ALLOW）
        assert len(checker1.check_calls) == 1
        assert len(checker2.check_calls) == 1

    def test_composite_permission_checker_2(self):
        """測試組合權限檢查器"""
        # 創建兩個檢查器
        checker1 = RejectingPermissionChecker()
        checker2 = DoNothingPermissionChecker()

        # 創建組合檢查器
        composite = CompositePermissionChecker([checker1, checker2])

        self.resource_manager.event_handlers.append(PermissionEventHandler(composite))

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.resource_manager.get_meta("test:123")

        # 只有第一個檢查器應該被呼叫（因為它返回了 DENY
        assert len(checker1.check_calls) == 1
        assert len(checker2.check_calls) == 0

    def test_composite_permission_checker_3(self):
        """測試組合權限檢查器"""
        # 創建兩個檢查器
        checker1 = DoNothingPermissionChecker()
        checker2 = DoNothingPermissionChecker()

        # 創建組合檢查器
        composite = CompositePermissionChecker([checker1, checker2])

        self.resource_manager.event_handlers.append(PermissionEventHandler(composite))

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.resource_manager.get_meta("test:123")

        # 只有第一個檢查器應該被呼叫（因為它返回了 DENY
        assert len(checker1.check_calls) == 1
        assert len(checker2.check_calls) == 1

    def test_permission_context_with_method_args(self):
        """測試權限上下文包含方法參數"""
        checker = MockPermissionChecker()
        self.resource_manager.event_handlers.append(PermissionEventHandler(checker))

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            try:
                self.resource_manager.update("test:123", DataStruct(name="test"))
            except Exception:
                pass

        # 檢查權限上下文包含正確的方法參數
        # update 會調用 get_meta，所以會有多次權限檢查
        assert len(checker.check_calls) >= 1
        # 找到 update 的權限檢查
        update_context = None
        for context in checker.check_calls:
            if context.action == ResourceAction.update:
                update_context = context
                break

        assert update_context is not None


class TestRbacPermissionCheck:
    @pytest.fixture(autouse=True)
    def setup_method(self):
        storage_factory = MemoryStorageFactory()
        checker = RBACPermissionChecker(root_user="admin")
        self.rm1 = ResourceManager(
            resource_type=DataStruct,
            name="DataStruct",
            storage=storage_factory.build("DataStruct"),
            permission_checker=checker,
        )
        self.rm2 = ResourceManager(
            resource_type=DataStruct,
            name="DataStruct2",
            storage=storage_factory.build("DataStruct2"),
            permission_checker=checker,
        )
        with self.rm1.meta_provide("admin", dt.datetime.now()):
            self.rm1.create(DataStruct(name="test1"))
            self.rm1.create(DataStruct(name="test2"))
            self.rm1.create(DataStruct(name="test3"))
        with self.rm1.meta_provide("admin", dt.datetime.now()):
            self.rm1.create(DataStruct2(title="test1"))
            self.rm1.create(DataStruct2(title="test2"))
            self.rm1.create(DataStruct2(title="test3"))
        with checker.resource_manager.meta_provide("admin", dt.datetime.now()):
            checker.resource_manager.create(
                RoleMembership(
                    subject="alice",
                    group="a**",
                ),
            )
            checker.resource_manager.create(
                RoleMembership(
                    subject="amy",
                    group="a**",
                ),
            )
            checker.resource_manager.create(
                RoleMembership(
                    subject="bob",
                    group="b**",
                ),
            )
            checker.resource_manager.create(
                RoleMembership(
                    subject="cat",
                    group="admin",
                ),
            )
            checker.resource_manager.create(
                RBACPermissionEntry(
                    subject="cat",
                    object="DataStruct2",
                    action=ResourceAction.full,
                    effect=PermissionResult.deny,
                ),
            )
            checker.resource_manager.create(
                RBACPermissionEntry(
                    subject="a**",
                    object="DataStruct",
                    action=ResourceAction.read | ResourceAction.create,
                    effect=PermissionResult.allow,
                ),
            )
            checker.resource_manager.create(
                RBACPermissionEntry(
                    subject="b**",
                    object="DataStruct",
                    action=ResourceAction.read,
                    effect=PermissionResult.allow,
                ),
            )
            checker.resource_manager.create(
                RBACPermissionEntry(
                    subject="b**",
                    object="DataStruct2",
                    action=ResourceAction.read | ResourceAction.create,
                    effect=PermissionResult.allow,
                ),
            )

    def test_1xx(self):
        with self.rm1.meta_provide("alice", dt.datetime.now()):
            rv1 = self.rm1.create(DataStruct(name="test4"))
        with self.rm1.meta_provide("amy", dt.datetime.now()):
            rv2 = self.rm1.create(DataStruct(name="test5"))
        with self.rm1.meta_provide("bob", dt.datetime.now()):
            self.rm1.get(rv1.resource_id)
        with self.rm1.meta_provide("b**", dt.datetime.now()):
            self.rm1.get(rv2.resource_id)
        with self.rm2.meta_provide("bob", dt.datetime.now()):
            rv3 = self.rm2.create(DataStruct2(title="title8"))
        with self.rm2.meta_provide("b**", dt.datetime.now()):
            rv4 = self.rm2.create(DataStruct2(title="title9"))
        with self.rm2.meta_provide("alice", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.rm2.get(rv3.resource_id)
        with self.rm2.meta_provide("amy", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.rm2.get(rv3.resource_id)
        with self.rm2.meta_provide("cat", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.rm2.get(rv4.resource_id)


if __name__ == "__main__":
    # 運行測試
    pytest.main([__file__, "-v"])
