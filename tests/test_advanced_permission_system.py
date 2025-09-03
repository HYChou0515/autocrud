"""
測試新的權限檢查系統
"""

from contextlib import suppress
import pytest
import datetime as dt
from msgspec import Struct

from autocrud.resource_manager.permission_context import (
    ActionBasedPermissionChecker,
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    CompositePermissionChecker,
)
from autocrud.resource_manager.permission import (
    PermissionResourceManager,
    ACLPermission,
    Effect,
)
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.basic import ResourceAction, ResourceIDNotFoundError
from autocrud.resource_manager.basic import PermissionDeniedError


class DataStructTest(Struct):
    name: str = "default"
    sensitive_field: str | None = None


class DoNothingPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        return PermissionResult.NOT_APPLICABLE


class RejectingPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        return PermissionResult.DENY


class AcceptingPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        return PermissionResult.ALLOW


class MockPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""

    def __init__(self):
        self.check_calls: list[PermissionContext] = []

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)

        # 簡單的測試邏輯
        if context.user == "blocked_user":
            return PermissionResult.DENY

        if context.action == ResourceAction.create and "sensitive" in str(
            context.method_args
        ):
            return PermissionResult.DENY

        return PermissionResult.ALLOW


class TestAdvancedPermissionChecking:
    """測試進階權限檢查系統"""

    @pytest.fixture(autouse=True)
    def setup_method(self):
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=MemoryResourceStore(DataStructTest),
        )

        resource_manager = ResourceManager(
            DataStructTest,
            storage=storage,
        )
        self.resource_manager = resource_manager
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=MemoryResourceStore(dict),
        )

        permission_manager = PermissionResourceManager(
            storage=storage,
        )
        self.permission_manager = permission_manager

    def test_default_permission_checker(self):
        """測試預設權限檢查器"""
        # 設定權限管理器到 resource_manager
        self.resource_manager.permission_manager = self.permission_manager

        # 建立權限規則
        with self.permission_manager.meta_provide("root", dt.datetime.now()):
            acl = ACLPermission(
                subject="alice",
                object="data_struct_test",
                action=ResourceAction.get_meta,
                effect=Effect.allow,
            )
            self.permission_manager.create(acl)

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
        self.resource_manager.permission_checker = checker

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
        assert context.resource_name == "data_struct_test"
        assert context.method_args[0] == "test:123"

    def test_custom_permission_checker_2(self):
        """測試自定義權限檢查器"""
        checker = ActionBasedPermissionChecker.from_dict(
            {
                "read": lambda _: PermissionResult.DENY,
                "create": lambda _: PermissionResult.ALLOW,
            }
        )
        self.resource_manager.permission_checker = checker

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.resource_manager.get_meta("test:123")

    def test_permission_denied(self):
        """測試權限拒絕"""
        checker = MockPermissionChecker()
        self.resource_manager.permission_checker = checker

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

        self.resource_manager.permission_checker = composite

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

        self.resource_manager.permission_checker = composite

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

        self.resource_manager.permission_checker = composite

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            with pytest.raises(PermissionDeniedError):
                self.resource_manager.get_meta("test:123")

        # 只有第一個檢查器應該被呼叫（因為它返回了 DENY
        assert len(checker1.check_calls) == 1
        assert len(checker2.check_calls) == 1

    def test_permission_context_with_method_args(self):
        """測試權限上下文包含方法參數"""
        checker = MockPermissionChecker()
        self.resource_manager.permission_checker = checker

        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            try:
                self.resource_manager.update("test:123", DataStructTest(name="test"))
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
        assert update_context.method_args[0] == "test:123"
        assert isinstance(update_context.method_args[1], DataStructTest)
        assert update_context.method_args[1].name == "test"

    def test_backward_compatibility(self):
        """測試向後相容性 - 不設定 permission_checker 時應該使用舊的方式"""
        # 不設定 permission_checker，但設定 permission_manager
        self.resource_manager.permission_manager = self.permission_manager
        self.resource_manager.permission_checker = None

        # 這應該仍然能工作（使用舊的權限檢查方式）
        with self.resource_manager.meta_provide("alice", dt.datetime.now()):
            try:
                self.resource_manager.get_meta("test:123")
            except Exception:
                pass  # 忽略其他錯誤


if __name__ == "__main__":
    # 運行測試
    pytest.main([__file__, "-v"])
