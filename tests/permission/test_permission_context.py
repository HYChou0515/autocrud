#!/usr/bin/env python3
"""權限上下文系統測試

測試權限上下文（PermissionContext）和相關的權限檢查器，包括：
- 權限上下文的建立和使用
- 各種權限檢查器的功能
- 組合權限檢查器的邏輯
- 與實際 ResourceManager 的整合
"""

import datetime as dt
from dataclasses import dataclass

import pytest

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker
from autocrud.permission.action import ActionBasedPermissionChecker
from autocrud.types import (
    BeforeCreate,
    BeforeDelete,
    BeforeGet,
    BeforeUpdate,
    PermissionResult,
)
from autocrud.permission.composite import (
    CompositePermissionChecker,
    ConditionalPermissionChecker,
)
from autocrud.permission.data_based import FieldLevelPermissionChecker
from autocrud.permission.meta_based import ResourceOwnershipChecker
from autocrud.types import PermissionContext, ResourceAction
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


@dataclass
class TestDocument:
    title: str
    content: str
    status: str = "draft"


class TestCaseUtil:
    @pytest.fixture(autouse=True)
    def setup_context_system(self):
        """設置權限上下文測試系統"""
        # 設定基本組件
        resource_store = MemoryResourceStore(TestDocument)
        storage = SimpleStorage(
            meta_store=MemoryMetaStore(),
            resource_store=resource_store,
        )

        # 設定權限管理器
        permission_checker = ACLPermissionChecker()

        # 建立 document manager
        document_manager = ResourceManager(
            TestDocument,
            storage=storage,
            permission_checker=permission_checker,
        )
        self.pc = permission_checker
        self.document_manager = document_manager
        self.current_time = dt.datetime.now()


class TestActionBasedPermissionChecker(TestCaseUtil):
    """測試基於 Action 的權限檢查器"""

    def test_action_handler_registration(self):
        """測試 action 處理器註冊"""
        checker = ActionBasedPermissionChecker()

        def create_handler(context: PermissionContext):
            return (
                PermissionResult.allow
                if context.user == "admin"
                else PermissionResult.deny
            )

        checker.register_action_handler("create", create_handler)

        # 測試 admin 用戶
        context = BeforeCreate(
            user="admin",
            now=dt.datetime.now(),
            resource_name="documents",
            data={"title": "Test", "content": "Content"},
        )
        result = checker.check_permission(context)
        assert result == PermissionResult.allow

        # 測試普通用戶
        context = BeforeCreate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            data={"title": "Test", "content": "Content"},
        )
        result = checker.check_permission(context)
        assert result == PermissionResult.deny

    def test_action_handler_registration2(self):
        """測試 action 處理器註冊"""
        checker = ActionBasedPermissionChecker.from_dict(
            {
                ResourceAction.create: [
                    lambda ctx: (
                        PermissionResult.allow
                        if ctx.user == "admin"
                        else PermissionResult.not_applicable
                    ),
                    lambda ctx: (
                        PermissionResult.allow
                        if ctx.user == "admin"
                        else PermissionResult.deny
                    ),
                ],
            },
        )

        # 測試普通用戶
        context = BeforeCreate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            data={"title": "Test", "content": "Content"},
        )
        result = checker.check_permission(context)
        assert result == PermissionResult.deny

    def test_unregistered_action(self):
        """測試未註冊的 action"""
        checker = ActionBasedPermissionChecker()

        context = BeforeCreate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            data={"title": "Test", "content": "Content"},
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.not_applicable


class TestFieldLevelPermissionChecker(TestCaseUtil):
    """測試欄位級權限檢查器"""

    def test_field_level_permissions(self):
        """測試欄位級權限"""
        field_permissions = {"alice": {"title", "content"}, "bob": {"status"}}

        checker = FieldLevelPermissionChecker(allowed_fields_by_user=field_permissions)

        # 測試 alice 修改允許的欄位
        context = BeforeUpdate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            resource_id="doc123",
            data={"title": "new title", "content": "new content"},
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.allow

        # 測試 alice 修改不允許的欄位
        context = BeforeUpdate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            resource_id="doc123",
            data={"status": "published"},  # alice 不能修改 status
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.deny

    def test_non_update_action(self):
        """測試非 update 操作"""
        checker = FieldLevelPermissionChecker()

        context = BeforeGet(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            resource_id="doc123",
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.not_applicable


class TestConditionalPermissionChecker(TestCaseUtil):
    """測試條件式權限檢查器"""

    def test_conditional_checker(self):
        """測試條件式檢查器"""
        checker = ConditionalPermissionChecker()

        # 添加條件：拒絕刪除操作
        def no_delete(context: PermissionContext):
            if ResourceAction.delete in context.action:
                return PermissionResult.deny
            return PermissionResult.not_applicable

        checker.add_condition(no_delete)

        # 測試刪除操作
        context = BeforeDelete(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            resource_id="doc456",
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.deny

        # 測試其他操作
        context = BeforeGet(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            resource_id="doc456",
        )

        result = checker.check_permission(context)
        assert (
            result == PermissionResult.not_applicable
        )  # 沒有條件阻止，返回 NOT_APPLICABLE

    def test_multiple_conditions(self):
        """測試多個條件"""
        checker = ConditionalPermissionChecker()

        # 條件1：工作時間才能修改
        def work_hours_only(context):
            if context.action in [ResourceAction.update, ResourceAction.create]:
                current_hour = context.now.hour
                if 9 <= current_hour <= 17:  # 9AM-5PM
                    return PermissionResult.not_applicable  # 繼續檢查
                return PermissionResult.deny  # 非工作時間拒絕
            return PermissionResult.not_applicable

        # 條件2：管理員例外
        def admin_exception(context):
            if context.user == "admin":
                return PermissionResult.allow  # 管理員總是允許
            return PermissionResult.not_applicable

        checker.add_condition(admin_exception)  # 先檢查管理員例外
        checker.add_condition(work_hours_only)  # 再檢查工作時間

        # 測試管理員用戶（應該總是允許）
        context = BeforeUpdate(
            user="admin",
            now=dt.datetime.now(),
            resource_name="documents",
            resource_id="doc456",
            data={"title": "Updated Title"},
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.allow


class TestCompositePermissionChecker(TestCaseUtil):
    """測試組合權限檢查器"""

    def test_composite_checker_first_deny_wins(self):
        """測試組合檢查器：第一個 DENY 獲勝"""

        # 第一個檢查器總是拒絕
        class AlwaysDenyChecker:
            def check_permission(self, context):
                return PermissionResult.deny

        # 第二個檢查器總是允許
        class AlwaysAllowChecker:
            def check_permission(self, context):
                return PermissionResult.allow

        composite = CompositePermissionChecker(
            [AlwaysDenyChecker(), AlwaysAllowChecker()],
        )

        context = BeforeCreate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            data={},
        )

        result = composite.check_permission(context)
        assert result == PermissionResult.deny

    def test_composite_checker_skip_not_applicable(self):
        """測試組合檢查器：跳過 NOT_APPLICABLE"""

        class NotApplicableChecker:
            def check_permission(self, context):
                return PermissionResult.not_applicable

        class AllowChecker:
            def check_permission(self, context):
                return PermissionResult.allow

        composite = CompositePermissionChecker([NotApplicableChecker(), AllowChecker()])

        context = BeforeCreate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            data={},
        )

        result = composite.check_permission(context)
        assert result == PermissionResult.allow


class MockResourceManager:
    """模擬 ResourceManager 用於測試"""

    def get_meta(self, resource_id):
        """模擬獲取資源元資料"""

        class MockMeta:
            def __init__(self, created_by):
                self.created_by = created_by

        # 模擬資料：doc123 由 alice 創建，doc456 由 bob 創建
        if resource_id == "doc123":
            return MockMeta("alice")
        if resource_id == "doc456":
            return MockMeta("bob")
        raise Exception("Resource not found")


class TestResourceOwnershipChecker(TestCaseUtil):
    """測試資源所有權檢查器"""

    def test_owner_can_update(self):
        """測試擁有者可以更新"""
        mock_rm = MockResourceManager()
        checker = ResourceOwnershipChecker(mock_rm)

        context = BeforeGet(
            user="alice",
            now=dt.datetime.now(),
            resource_id="doc123",
            resource_name="documents",
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.allow

    def test_non_owner_cannot_update(self):
        """測試非擁有者不能更新"""
        mock_rm = MockResourceManager()
        checker = ResourceOwnershipChecker(mock_rm)

        context = BeforeGet(
            user="alice",
            now=dt.datetime.now(),
            resource_id="doc456",
            resource_name="documents",
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.deny

    def test_non_applicable_action(self):
        """測試不適用的操作"""
        mock_rm = MockResourceManager()
        checker = ResourceOwnershipChecker(
            mock_rm,
            allowed_actions={ResourceAction.update, ResourceAction.delete},
        )

        context = BeforeCreate(
            user="alice",
            now=dt.datetime.now(),
            resource_name="documents",
            data={},
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.not_applicable


class TestDefaultPermissionChecker(TestCaseUtil):
    """測試默認權限檢查器"""

    def test_default_checker_integration(self):
        """測試默認檢查器與實際權限系統的整合"""
        pm = self.pc.pm
        current_time = self.current_time

        # 設置權限
        with pm.meta_provide("root", current_time):
            # Alice 有讀取和更新權限
            alice_permissions = ACLPermission(
                subject="alice",
                object="documents",
                action=ResourceAction.get | ResourceAction.update,
                effect=PermissionResult.allow,
            )
            pm.create(alice_permissions)

        # 創建默認檢查器
        checker = self.pc

        # 測試允許的操作
        context = BeforeGet(
            user="alice",
            now=current_time,
            resource_name="documents",
            resource_id="doc456",
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.allow

        # 測試不允許的操作
        context = BeforeCreate(
            user="alice",
            now=current_time,
            resource_name="documents",
            data={},
        )

        result = checker.check_permission(context)
        assert result == PermissionResult.deny


# 整合測試
class TestIntegratedPermissionContextSystem(TestCaseUtil):
    """測試整合的權限上下文系統"""

    def test_realistic_scenario(self):
        """測試真實場景"""
        pm = self.pc.pm
        dm = self.document_manager
        current_time = self.current_time

        # 設置權限
        with pm.meta_provide("root", current_time):
            # Editor 有完整權限
            editor_permissions = ACLPermission(
                subject="editor",
                object="test_document",
                action=ResourceAction.create
                | ResourceAction.get
                | ResourceAction.update,
                effect=PermissionResult.allow,
            )
            pm.create(editor_permissions)

            # User 只有讀取權限
            user_permissions = ACLPermission(
                subject="user",
                object="test_document",
                action=ResourceAction.get,
                effect=PermissionResult.allow,
            )
            pm.create(user_permissions)

        # 創建文檔
        with dm.meta_provide("editor", current_time):
            doc = TestDocument(
                title="API Test Doc",
                content="API Test Content",
                status="draft",
            )
            doc_info = dm.create(doc)
            doc_id = doc_info.resource_id

        # 設置欄位級權限檢查
        field_checker = FieldLevelPermissionChecker(
            allowed_fields_by_user={
                "editor": {"title", "content", "status"},
                "user": set(),  # 普通用戶不能修改任何欄位
            },
        )

        # 設置默認權限檢查
        default_checker = self.pc

        # 組合所有檢查器
        composite = CompositePermissionChecker(
            [
                field_checker,  # 先檢查欄位權限
                default_checker,  # 再檢查基本權限
            ],
        )

        # 測試場景 1: Editor 更新文檔
        context = BeforeUpdate(
            user="editor",
            now=current_time,
            resource_name="test_document",
            resource_id=doc_id,
            data={},
        )

        result = composite.check_permission(context)
        assert result == PermissionResult.allow

        # 測試場景 2: 普通用戶嘗試更新文檔（欄位權限拒絕）
        context = BeforeUpdate(
            user="user",
            now=current_time,
            resource_name="test_document",
            resource_id=doc_id,
            data={},
        )

        result = composite.check_permission(context)
        assert result == PermissionResult.deny  # 被欄位檢查器拒絕

        # 測試場景 3: 普通用戶讀取文檔（應該允許）
        context = BeforeGet(
            user="user",
            now=current_time,
            resource_name="test_document",
            resource_id=doc_id,
        )

        result = composite.check_permission(context)
        assert result == PermissionResult.allow

    def test_complex_business_rules(self):
        """測試複雜的業務規則"""
        # 業務規則：
        # 1. 只有工作時間才能創建文檔
        # 2. 管理員例外

        conditional_checker = ConditionalPermissionChecker()

        # 規則1: 工作時間限制（但管理員例外）
        def work_hours_rule(context):
            if context.action == ResourceAction.create and context.user != "admin":
                current_hour = context.now.hour
                if not (9 <= current_hour <= 17):
                    return PermissionResult.deny
            return PermissionResult.not_applicable

        conditional_checker.add_condition(work_hours_rule)

        # 測試非工作時間的創建
        non_work_time = dt.datetime.now().replace(hour=20)  # 晚上8點
        context = BeforeCreate(
            user="alice",
            now=non_work_time,
            resource_name="documents",
            data={"title": "After Hours Doc"},
        )

        result = conditional_checker.check_permission(context)
        assert result == PermissionResult.deny

        # 測試管理員在非工作時間創建（應該允許）
        context = BeforeCreate(
            user="admin",
            now=non_work_time,
            resource_name="documents",
            data={"title": "Admin After Hours Doc"},
        )

        result = conditional_checker.check_permission(context)
        assert result == PermissionResult.not_applicable  # 管理員不受工作時間限制


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
