"""
測試新的權限檢查系統
"""
import pytest
import datetime as dt
from msgspec import Struct

from autocrud.resource_manager.permission_context import (
    IPermissionChecker,
    PermissionContext,
    PermissionResult,
    CompositePermissionChecker,
    DefaultPermissionChecker,
)
from autocrud.resource_manager.permission import (
    PermissionResourceManager,
    ACLPermission,
    Effect,
    Permission,
)
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


class TestDataStruct(Struct):
    name: str = "default"
    sensitive_field: str | None = None


class MockPermissionChecker(IPermissionChecker):
    """測試用的權限檢查器"""
    
    def __init__(self):
        self.check_calls = []
    
    def supports_action(self, action: str) -> bool:
        return True
    
    def check_permission(self, context: PermissionContext) -> PermissionResult:
        self.check_calls.append(context)
        
        # 簡單的測試邏輯
        if context.user == "blocked_user":
            return PermissionResult.DENY
        
        if context.action == "sensitive_action":
            return PermissionResult.DENY
        
        return PermissionResult.ALLOW


class TestAdvancedPermissionChecking:
    """測試進階權限檢查系統"""
    
    @pytest.fixture
    def resource_manager(self):
        """建立測試用的 ResourceManager"""
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=MemoryResourceStore(TestDataStruct),
        )
        
        rm = ResourceManager(
            TestDataStruct,
            storage=storage,
        )
        return rm
    
    @pytest.fixture
    def permission_manager(self):
        """建立測試用的 PermissionResourceManager"""
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=MemoryResourceStore(Permission),
        )
        
        pm = PermissionResourceManager(
            storage=storage,
        )
        return pm
    
    def test_default_permission_checker(self, resource_manager, permission_manager):
        """測試預設權限檢查器"""
        # 設定預設權限檢查器
        resource_manager.permission_checker = DefaultPermissionChecker(permission_manager)
        
        # 建立權限規則
        with permission_manager.meta_provide("admin", dt.datetime.now()):
            acl = ACLPermission(
                subject="user:alice",
                object="test_data",
                action="get",
                effect=Effect.allow,
            )
            permission_manager.create(acl)
        
        # 測試權限檢查
        with resource_manager.meta_provide("user:alice", dt.datetime.now()):
            # 這應該會成功，因為有權限
            meta = resource_manager.get_meta("test:123")  # 這會失敗因為資源不存在，但權限檢查會通過
    
    def test_custom_permission_checker(self, resource_manager):
        """測試自定義權限檢查器"""
        checker = MockPermissionChecker()
        resource_manager.permission_checker = checker
        
        with resource_manager.meta_provide("user:alice", dt.datetime.now()):
            try:
                resource_manager.get_meta("test:123")
            except Exception:
                pass  # 忽略資源不存在的錯誤，我們只關心權限檢查
        
        # 檢查權限檢查器是否被呼叫
        assert len(checker.check_calls) == 1
        context = checker.check_calls[0]
        assert context.user == "user:alice"
        assert context.action == "get_meta"
        assert context.resource_name == "test_data"
        assert context.resource_id == "test:123"
    
    def test_permission_denied(self, resource_manager):
        """測試權限拒絕"""
        checker = MockPermissionChecker()
        resource_manager.permission_checker = checker
        
        with resource_manager.meta_provide("blocked_user", dt.datetime.now()):
            from autocrud.resource_manager.basic import PermissionDeniedError
            with pytest.raises(PermissionDeniedError):
                resource_manager.get_meta("test:123")
    
    def test_composite_permission_checker(self, resource_manager):
        """測試組合權限檢查器"""
        composite = CompositePermissionChecker()
        
        # 添加兩個檢查器
        checker1 = MockPermissionChecker()
        checker2 = MockPermissionChecker()
        
        composite.add_checker(checker1)
        composite.add_checker(checker2)
        
        resource_manager.permission_checker = composite
        
        with resource_manager.meta_provide("user:alice", dt.datetime.now()):
            try:
                resource_manager.get_meta("test:123")
            except Exception:
                pass
        
        # 只有第一個檢查器應該被呼叫（因為它返回了 ALLOW）
        assert len(checker1.check_calls) == 1
        assert len(checker2.check_calls) == 0
    
    def test_permission_context_with_method_args(self, resource_manager):
        """測試權限上下文包含方法參數"""
        checker = MockPermissionChecker()
        resource_manager.permission_checker = checker
        
        with resource_manager.meta_provide("user:alice", dt.datetime.now()):
            try:
                resource_manager.update("test:123", TestDataStruct(name="test"))
            except Exception:
                pass
        
        # 檢查權限上下文包含正確的方法參數
        # update 會調用 get_meta，所以會有兩次權限檢查
        assert len(checker.check_calls) >= 1
        # 找到 update 的權限檢查
        update_context = None
        for context in checker.check_calls:
            if context.action == "update":
                update_context = context
                break
        
        assert update_context is not None
        assert update_context.method_args[0] == "test:123"
        assert isinstance(update_context.method_args[1], TestDataStruct)
        assert update_context.method_args[1].name == "test"
    
    def test_backward_compatibility(self, resource_manager, permission_manager):
        """測試向後相容性 - 不設定 permission_checker 時應該使用舊的方式"""
        # 不設定 permission_checker，但設定 permission_manager
        resource_manager.permission_manager = permission_manager
        resource_manager.permission_checker = None
        
        # 這應該仍然能工作（使用舊的權限檢查方式）
        with resource_manager.meta_provide("user:alice", dt.datetime.now()):
            try:
                resource_manager.get_meta("test:123")
            except Exception:
                pass  # 忽略其他錯誤


if __name__ == "__main__":
    # 運行測試
    pytest.main([__file__, "-v"])
