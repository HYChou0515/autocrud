"""
測試新的權限檢查系統
"""

import pytest
from datetime import datetime
from autocrud.resource_manager.permission_context import (
    PermissionContext, PermissionResult, 
    DefaultPermissionChecker, CompositePermissionChecker,
    ResourceOwnershipChecker, FieldLevelPermissionChecker,
    ActionBasedPermissionChecker, ConditionalPermissionChecker
)
from autocrud.resource_manager.permission import PermissionResourceManager, ACLPermission, Effect


class TestPermissionContext:
    """測試權限檢查上下文系統"""
    
    def test_permission_context_creation(self):
        """測試 PermissionContext 建立"""
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            resource_id="doc123",
            method_name="get",
            method_args=("doc123",),
            method_kwargs={}
        )
        
        assert context.user == "user:alice"
        assert context.action == "get"
        assert context.resource_name == "documents"
        assert context.resource_id == "doc123"
        assert context.has_resource_id is True
        assert context.method_name == "get"
    
    def test_permission_context_without_resource_id(self):
        """測試沒有 resource_id 的情況"""
        context = PermissionContext(
            user="user:alice",
            action="create",
            resource_name="documents",
            method_name="create"
        )
        
        assert context.has_resource_id is False
        assert context.resource_id is None


class TestActionBasedPermissionChecker:
    """測試基於 Action 的權限檢查器"""
    
    def test_action_handler_registration(self):
        """測試 action 處理器註冊"""
        checker = ActionBasedPermissionChecker()
        
        def create_handler(context):
            return PermissionResult.ALLOW if context.user == "user:admin" else PermissionResult.DENY
        
        checker.register_action_handler("create", create_handler)
        
        # 測試 admin 用戶
        context = PermissionContext(
            user="user:admin",
            action="create",
            resource_name="documents",
            method_name="create"
        )
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試普通用戶
        context = PermissionContext(
            user="user:alice",
            action="create",
            resource_name="documents",
            method_name="create"
        )
        result = checker.check_permission(context)
        assert result == PermissionResult.DENY
    
    def test_unregistered_action(self):
        """測試未註冊的 action"""
        checker = ActionBasedPermissionChecker()
        
        context = PermissionContext(
            user="user:alice",
            action="unknown_action",
            resource_name="documents",
            method_name="unknown_method"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.NOT_APPLICABLE


class TestFieldLevelPermissionChecker:
    """測試欄位級權限檢查器"""
    
    def test_field_level_permissions(self):
        """測試欄位級權限"""
        field_permissions = {
            "user:alice": {"name", "email"},
            "user:bob": {"description"}
        }
        
        checker = FieldLevelPermissionChecker(allowed_fields_by_user=field_permissions)
        
        # 測試 alice 修改允許的欄位
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",
            method_name="update",
            method_kwargs={"data": {"name": "new name", "email": "new@email.com"}}
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試 alice 修改不允許的欄位
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",
            method_name="update",
            method_kwargs={"data": {"status": "published"}}  # alice 不能修改 status
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.DENY
    
    def test_non_update_action(self):
        """測試非 update 操作"""
        checker = FieldLevelPermissionChecker()
        
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            resource_id="doc123",
            method_name="get"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.NOT_APPLICABLE


class TestConditionalPermissionChecker:
    """測試條件式權限檢查器"""
    
    def test_conditional_checker(self):
        """測試條件式檢查器"""
        checker = ConditionalPermissionChecker()
        
        # 添加條件：拒絕刪除操作
        def no_delete(context):
            if context.action == "delete":
                return PermissionResult.DENY
            return PermissionResult.NOT_APPLICABLE
        
        checker.add_condition(no_delete)
        
        # 測試刪除操作
        context = PermissionContext(
            user="user:alice",
            action="delete",
            resource_name="documents",
            resource_id="doc123",
            method_name="delete"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.DENY
        
        # 測試其他操作
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            resource_id="doc123",
            method_name="get"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW  # 沒有條件阻止


class TestCompositePermissionChecker:
    """測試組合權限檢查器"""
    
    def test_composite_checker_first_deny_wins(self):
        """測試組合檢查器：第一個 DENY 獲勝"""
        
        # 第一個檢查器總是拒絕
        class AlwaysDenyChecker:
            def check_permission(self, context):
                return PermissionResult.DENY
        
        # 第二個檢查器總是允許
        class AlwaysAllowChecker:
            def check_permission(self, context):
                return PermissionResult.ALLOW
        
        composite = CompositePermissionChecker([
            AlwaysDenyChecker(),
            AlwaysAllowChecker()
        ])
        
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            method_name="get"
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.DENY
    
    def test_composite_checker_skip_not_applicable(self):
        """測試組合檢查器：跳過 NOT_APPLICABLE"""
        
        class NotApplicableChecker:
            def check_permission(self, context):
                return PermissionResult.NOT_APPLICABLE
        
        class AllowChecker:
            def check_permission(self, context):
                return PermissionResult.ALLOW
        
        composite = CompositePermissionChecker([
            NotApplicableChecker(),
            AllowChecker()
        ])
        
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            method_name="get"
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.ALLOW


class MockResourceManager:
    """模擬 ResourceManager 用於測試"""
    
    def get_meta(self, resource_id):
        """模擬獲取資源元資料"""
        class MockMeta:
            def __init__(self, created_by):
                self.created_by = created_by
        
        # 模擬資料：doc123 由 alice 創建，doc456 由 bob 創建
        if resource_id == "doc123":
            return MockMeta("user:alice")
        elif resource_id == "doc456":
            return MockMeta("user:bob")
        else:
            raise Exception("Resource not found")


class TestResourceOwnershipChecker:
    """測試資源所有權檢查器"""
    
    def test_owner_can_update(self):
        """測試擁有者可以更新"""
        mock_rm = MockResourceManager()
        checker = ResourceOwnershipChecker(mock_rm)
        
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",  # 由 alice 創建
            method_name="update"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW
    
    def test_non_owner_cannot_update(self):
        """測試非擁有者不能更新"""
        mock_rm = MockResourceManager()
        checker = ResourceOwnershipChecker(mock_rm)
        
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc456",  # 由 bob 創建
            method_name="update"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.DENY
    
    def test_non_applicable_action(self):
        """測試不適用的操作"""
        mock_rm = MockResourceManager()
        checker = ResourceOwnershipChecker(mock_rm, allowed_actions={"update", "delete"})
        
        context = PermissionContext(
            user="user:alice",
            action="get",  # get 不在 allowed_actions 中
            resource_name="documents",
            resource_id="doc123",
            method_name="get"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.NOT_APPLICABLE


# 整合測試
class TestIntegratedPermissionSystem:
    """測試整合的權限系統"""
    
    def test_realistic_scenario(self):
        """測試真實場景"""
        
        # 設置欄位級權限
        field_checker = FieldLevelPermissionChecker(
            allowed_fields_by_user={
                "user:alice": {"name", "description"},
                "user:admin": {"name", "description", "status", "priority"}
            }
        )
        
        # 設置資源所有權檢查
        mock_rm = MockResourceManager()
        ownership_checker = ResourceOwnershipChecker(mock_rm)
        
        # 設置條件式檢查
        conditional_checker = ConditionalPermissionChecker()
        conditional_checker.add_condition(
            lambda ctx: PermissionResult.DENY if ctx.action == "delete" and ctx.user != "user:admin" 
                       else PermissionResult.NOT_APPLICABLE
        )
        
        # 組合所有檢查器 - 條件檢查應該在前面，因為它包含更嚴格的規則
        composite = CompositePermissionChecker([
            conditional_checker,   # 先檢查條件（最嚴格）
            field_checker,        # 再檢查欄位權限（具體檢查）
            ownership_checker,     # 最後檢查所有權（一般性檢查）
        ])
        
        # 測試場景 1: alice 更新自己的文檔，修改允許的欄位
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",  # alice 的文檔
            method_name="update",
            method_kwargs={"data": {"name": "new name", "description": "new desc"}}
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試場景 2: alice 更新自己的文檔，但修改不允許的欄位
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",  # alice 的文檔
            method_name="update",
            method_kwargs={"data": {"status": "published"}}  # alice 不能修改 status
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.DENY
        
        # 測試場景 3: alice 嘗試刪除文檔（被條件式檢查拒絕）
        context = PermissionContext(
            user="user:alice",
            action="delete",
            resource_name="documents",
            resource_id="doc123",  # alice 的文檔
            method_name="delete"
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.DENY  # 只有 admin 可以刪除
