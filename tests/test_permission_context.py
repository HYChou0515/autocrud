#!/usr/bin/env python3
"""
權限上下文系統測試

測試權限上下文（PermissionContext）和相關的權限檢查器，包括：
- 權限上下文的建立和使用
- 各種權限檢查器的功能
- 組合權限檢查器的邏輯
- 與實際 ResourceManager 的整合
"""

import pytest
import datetime as dt
from dataclasses import dataclass
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore  
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.permission import PermissionResourceManager, ACLPermission, Effect
from autocrud.resource_manager.basic import ResourceAction
from autocrud.resource_manager.permission_context import (
    PermissionContext, PermissionResult, 
    DefaultPermissionChecker, CompositePermissionChecker,
    ResourceOwnershipChecker, FieldLevelPermissionChecker,
    ActionBasedPermissionChecker, ConditionalPermissionChecker
)


@dataclass
class TestDocument:
    title: str
    content: str
    status: str = "draft"


@pytest.fixture
def setup_context_system():
    """設置權限上下文測試系統"""
    # 設定基本組件
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(TestDocument)
    storage = SimpleStorage(meta_store=meta_store, resource_store=resource_store)
    
    # 設定權限管理器
    permission_resource_store = MemoryResourceStore(dict)
    permission_storage = SimpleStorage(meta_store=meta_store, resource_store=permission_resource_store)
    permission_manager = PermissionResourceManager(storage=permission_storage)
    
    # 建立 document manager
    document_manager = ResourceManager(TestDocument, storage=storage, permission_manager=permission_manager)
    
    return {
        'meta_store': meta_store,
        'permission_manager': permission_manager,
        'document_manager': document_manager,
        'current_time': dt.datetime.now()
    }


class TestPermissionContext:
    """測試權限檢查上下文系統"""
    
    def test_permission_context_creation(self):
        """測試 PermissionContext 建立"""
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            resource_id="doc123",
            method="GET",
            path="/documents/doc123",
            request_data={"include": "metadata"}
        )
        
        assert context.user == "user:alice"
        assert context.action == "get"
        assert context.resource_name == "documents"
        assert context.resource_id == "doc123"
        assert context.method == "GET"
        assert context.path == "/documents/doc123"
        assert context.request_data == {"include": "metadata"}
    
    def test_permission_context_without_resource_id(self):
        """測試沒有 resource_id 的情況"""
        context = PermissionContext(
            user="user:alice",
            action="create",
            resource_name="documents",
            method="POST",
            path="/documents",
            request_data={"title": "New Doc", "content": "New Content"}
        )
        
        assert context.resource_id is None
        assert context.method == "POST"
        assert context.request_data["title"] == "New Doc"


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
            method="POST",
            path="/documents"
        )
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試普通用戶
        context = PermissionContext(
            user="user:alice",
            action="create",
            resource_name="documents",
            method="POST",
            path="/documents"
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
            method="UNKNOWN",
            path="/documents"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.NOT_APPLICABLE


class TestFieldLevelPermissionChecker:
    """測試欄位級權限檢查器"""
    
    def test_field_level_permissions(self):
        """測試欄位級權限"""
        field_permissions = {
            "user:alice": {"title", "content"},
            "user:bob": {"status"}
        }
        
        checker = FieldLevelPermissionChecker(allowed_fields_by_user=field_permissions)
        
        # 測試 alice 修改允許的欄位
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",
            method="PUT",
            path="/documents/doc123",
            request_data={"title": "new title", "content": "new content"}
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試 alice 修改不允許的欄位
        context = PermissionContext(
            user="user:alice",
            action="update",
            resource_name="documents",
            resource_id="doc123",
            method="PUT",
            path="/documents/doc123",
            request_data={"status": "published"}  # alice 不能修改 status
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
            method="GET",
            path="/documents/doc123"
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
            method="DELETE",
            path="/documents/doc123"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.DENY
        
        # 測試其他操作
        context = PermissionContext(
            user="user:alice",
            action="get",
            resource_name="documents",
            resource_id="doc123",
            method="GET",
            path="/documents/doc123"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW  # 沒有條件阻止
    
    def test_multiple_conditions(self):
        """測試多個條件"""
        checker = ConditionalPermissionChecker()
        
        # 條件1：工作時間才能修改
        def work_hours_only(context):
            if context.action in ["update", "create"]:
                current_hour = dt.datetime.now().hour
                if 9 <= current_hour <= 17:  # 9AM-5PM
                    return PermissionResult.NOT_APPLICABLE  # 繼續檢查
                else:
                    return PermissionResult.DENY  # 非工作時間拒絕
            return PermissionResult.NOT_APPLICABLE
        
        # 條件2：管理員例外
        def admin_exception(context):
            if context.user == "user:admin":
                return PermissionResult.ALLOW  # 管理員總是允許
            return PermissionResult.NOT_APPLICABLE
        
        checker.add_condition(admin_exception)  # 先檢查管理員例外
        checker.add_condition(work_hours_only)  # 再檢查工作時間
        
        # 測試管理員用戶（應該總是允許）
        context = PermissionContext(
            user="user:admin",
            action="update",
            resource_name="documents",
            resource_id="doc123",
            method="PUT",
            path="/documents/doc123"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW


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
            method="GET",
            path="/documents"
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
            method="GET",
            path="/documents"
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
            method="PUT",
            path="/documents/doc123"
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
            method="PUT",
            path="/documents/doc456"
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
            method="GET",
            path="/documents/doc123"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.NOT_APPLICABLE


class TestDefaultPermissionChecker:
    """測試默認權限檢查器"""
    
    def test_default_checker_integration(self, setup_context_system):
        """測試默認檢查器與實際權限系統的整合"""
        pm = setup_context_system['permission_manager']
        meta_store = setup_context_system['meta_store']
        current_time = setup_context_system['current_time']
        
        # 設置權限
        with pm.meta_provide("system", current_time):
            # Alice 有讀取和更新權限
            alice_permissions = ACLPermission(
                subject="user:alice",
                object="documents",
                action=ResourceAction.read | ResourceAction.update,
                effect=Effect.allow
            )
            pm.create(alice_permissions)
        
        # 創建默認檢查器
        checker = DefaultPermissionChecker(pm)
        
        # 測試允許的操作
        context = PermissionContext(
            user="user:alice",
            action="read",
            resource_name="documents",
            resource_id="doc123",
            method="GET",
            path="/documents/doc123"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試不允許的操作
        context = PermissionContext(
            user="user:alice",
            action="delete",
            resource_name="documents",
            resource_id="doc123",
            method="DELETE",
            path="/documents/doc123"
        )
        
        result = checker.check_permission(context)
        assert result == PermissionResult.DENY


# 整合測試
class TestIntegratedPermissionContextSystem:
    """測試整合的權限上下文系統"""
    
    def test_realistic_api_scenario(self, setup_context_system):
        """測試真實的 API 場景"""
        pm = setup_context_system['permission_manager']
        dm = setup_context_system['document_manager']
        meta_store = setup_context_system['meta_store']
        current_time = setup_context_system['current_time']
        
        # 設置權限
        with pm.meta_provide("system", current_time):
            # Editor 有完整權限
            editor_permissions = ACLPermission(
                subject="user:editor",
                object="test_document",
                action=ResourceAction.create | ResourceAction.read | ResourceAction.update,
                effect=Effect.allow
            )
            pm.create(editor_permissions)
            
            # User 只有讀取權限
            user_permissions = ACLPermission(
                subject="user:user",
                object="test_document",
                action=ResourceAction.read,
                effect=Effect.allow
            )
            pm.create(user_permissions)
        
        # 創建文檔
        with dm.meta_provide("user:editor", current_time):
            doc = TestDocument(title="API Test Doc", content="API Test Content", status="draft")
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id
        
        # 設置欄位級權限檢查
        field_checker = FieldLevelPermissionChecker(
            allowed_fields_by_user={
                "user:editor": {"title", "content", "status"},
                "user:user": set()  # 普通用戶不能修改任何欄位
            }
        )
        
        # 設置資源所有權檢查
        ownership_checker = ResourceOwnershipChecker(dm)
        
        # 設置默認權限檢查
        default_checker = DefaultPermissionChecker(pm)
        
        # 組合所有檢查器
        composite = CompositePermissionChecker([
            field_checker,        # 先檢查欄位權限
            ownership_checker,    # 再檢查所有權
            default_checker,      # 最後檢查基本權限
        ])
        
        # 測試場景 1: Editor 更新自己的文檔
        context = PermissionContext(
            user="user:editor",
            action="update",
            resource_name="test_document",
            resource_id=doc_id,
            method="PUT",
            path=f"/documents/{doc_id}",
            request_data={"title": "Updated Title", "status": "published"}
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.ALLOW
        
        # 測試場景 2: 普通用戶嘗試更新文檔（欄位權限拒絕）
        context = PermissionContext(
            user="user:user",
            action="update",
            resource_name="test_document",
            resource_id=doc_id,
            method="PUT",
            path=f"/documents/{doc_id}",
            request_data={"title": "User's Update"}
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.DENY  # 被欄位檢查器拒絕
        
        # 測試場景 3: 普通用戶讀取文檔（應該允許）
        context = PermissionContext(
            user="user:user",
            action="read",
            resource_name="test_document",
            resource_id=doc_id,
            method="GET",
            path=f"/documents/{doc_id}"
        )
        
        result = composite.check_permission(context)
        assert result == PermissionResult.ALLOW
    
    def test_complex_business_rules(self):
        """測試複雜的業務規則"""
        
        # 業務規則：
        # 1. 只有工作時間才能創建文檔
        # 2. 管理員例外
        # 3. 文檔狀態為 "locked" 時不能修改
        # 4. 只能修改自己創建的文檔
        
        conditional_checker = ConditionalPermissionChecker()
        
        # 規則1: 工作時間限制（但管理員例外）
        def work_hours_rule(context):
            if context.action == "create" and context.user != "user:admin":
                current_hour = dt.datetime.now().hour
                if not (9 <= current_hour <= 17):
                    return PermissionResult.DENY
            return PermissionResult.NOT_APPLICABLE
        
        # 規則2: 鎖定文檔不能修改
        def locked_document_rule(context):
            if context.action == "update" and context.request_data:
                # 假設我們能獲取現有文檔狀態
                if hasattr(context, 'current_document_status') and context.current_document_status == "locked":
                    return PermissionResult.DENY
            return PermissionResult.NOT_APPLICABLE
        
        conditional_checker.add_condition(work_hours_rule)
        conditional_checker.add_condition(locked_document_rule)
        
        # 測試工作時間外的創建（假設現在不是工作時間）
        context = PermissionContext(
            user="user:alice",
            action="create",
            resource_name="documents",
            method="POST",
            path="/documents",
            request_data={"title": "After Hours Doc"}
        )
        
        # 模擬非工作時間（假設現在是晚上10點）
        if dt.datetime.now().hour < 9 or dt.datetime.now().hour > 17:
            result = conditional_checker.check_permission(context)
            assert result == PermissionResult.DENY
        
        # 測試管理員在非工作時間創建（應該允許）
        context = PermissionContext(
            user="user:admin",
            action="create",
            resource_name="documents",
            method="POST",
            path="/documents",
            request_data={"title": "Admin After Hours Doc"}
        )
        
        result = conditional_checker.check_permission(context)
        assert result == PermissionResult.NOT_APPLICABLE  # 管理員不受工作時間限制


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
