"""完整的權限設定和使用示例"""

import datetime as dt
from dataclasses import dataclass

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker, Policy
from autocrud.types import (
    PermissionResult,
)
from autocrud.permission.composite import (
    CompositePermissionChecker,
    ConditionalPermissionChecker,
)
from autocrud.permission.data_based import FieldLevelPermissionChecker
from autocrud.permission.meta_based import ResourceOwnershipChecker
from autocrud.types import IPermissionChecker, PermissionContext, ResourceAction
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


# 示例資料結構
@dataclass
class Document:
    title: str
    content: str
    status: str = "draft"  # draft, published, archived
    category: str = "general"


class DocumentPermissionChecker(IPermissionChecker):
    """自定義文檔權限檢查器"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """實現文檔特定的權限邏輯"""
        # 1. 草稿狀態的文檔只有作者可以查看
        if context.action == ResourceAction.get and context.resource_data:
            if hasattr(context.resource_data, "status"):
                if context.resource_data.status == "draft":
                    # 需要檢查是否為作者（通過所有權檢查器處理）
                    return PermissionResult.not_applicable

        # 2. 只有編輯者可以發布文檔
        if context.action == ResourceAction.update and context.method_kwargs.get(
            "data",
        ):
            data = context.method_kwargs["data"]
            if hasattr(data, "status") and data.status == "published":
                if context.user not in ["carol", "david"]:  # carol=editor, david=admin
                    return PermissionResult.deny

        # 3. 歸檔文檔不能修改
        if (
            context.action in ResourceAction.update | ResourceAction.patch
            and context.resource_data
        ):
            if hasattr(context.resource_data, "status"):
                if context.resource_data.status == "archived":
                    return PermissionResult.deny

        return PermissionResult.not_applicable


def setup_document_permission_system():
    """設定文檔管理的權限系統"""
    # 1. 創建儲存
    doc_meta_store = MemoryMetaStore()
    doc_resource_store = MemoryResourceStore(Document)
    doc_storage = SimpleStorage(
        meta_store=doc_meta_store,
        resource_store=doc_resource_store,
    )

    # 2. 創建權限檢查器（不需要權限管理器）
    permission_checker = ACLPermissionChecker(policy=Policy.strict, root_user="system")

    # 3. 創建文檔管理器
    document_manager = ResourceManager(
        resource_type=Document,
        storage=doc_storage,
        permission_checker=permission_checker,
    )

    # 4. 設定權限檢查器

    # 4.1 欄位級權限
    field_checker = FieldLevelPermissionChecker(
        allowed_fields_by_user={
            "alice": {"title", "content"},  # 作者只能修改標題和內容
            "bob": {"title", "content"},
            "carol": {
                "title",
                "content",
                "status",
                "category",
            },  # 編輯者可以改狀態
            "david": {"title", "content", "status", "category"},  # 管理員全權限
        },
    )

    # 4.2 資源所有權檢查
    ownership_checker = ResourceOwnershipChecker(
        resource_manager=document_manager,
        allowed_actions={
            ResourceAction.get,
            ResourceAction.update,
            ResourceAction.patch,
            ResourceAction.delete,
        },
    )

    # 4.3 條件式檢查
    conditional_checker = ConditionalPermissionChecker()

    # 只有管理員可以刪除
    conditional_checker.add_condition(
        lambda ctx: PermissionResult.deny
        if ctx.action == ResourceAction.delete and ctx.user != "david"
        else PermissionResult.not_applicable,
    )

    # 週末不能發布文檔
    def no_weekend_publish(context):
        if context.action == ResourceAction.update and context.method_kwargs.get(
            "data",
        ):
            data = context.method_kwargs["data"]
            if hasattr(data, "status") and data.status == "published":
                if dt.datetime.now().weekday() >= 5:  # 週末
                    return PermissionResult.deny
        return PermissionResult.not_applicable

    conditional_checker.add_condition(no_weekend_publish)

    # 4.4 自定義文檔權限檢查
    document_checker = DocumentPermissionChecker()

    # 4.5 組合所有檢查器
    composite_checker = CompositePermissionChecker(
        [
            conditional_checker,  # 最高優先級：條件限制
            document_checker,  # 文檔特定邏輯
            field_checker,  # 欄位權限
            ownership_checker,  # 所有權檢查
            permission_checker,  # 基本 ACL/RBAC
        ],
    )

    # 5. 將權限檢查器設定到文檔管理器
    document_manager.permission_checker = composite_checker

    return document_manager, permission_checker


def setup_initial_permissions(permission_checker: ACLPermissionChecker):
    """設定初始權限資料"""
    admin_user = "system"
    current_time = dt.datetime.now()

    with permission_checker.resource_manager.meta_provide(admin_user, current_time):
        # 創建 ACL 權限（簡化版本，不使用角色成員關係）
        acl_permissions = [
            # alice 可以創建和操作文檔
            ACLPermission(
                subject="alice",
                object="document",
                action=ResourceAction.write | ResourceAction.read,
                effect=PermissionResult.allow,
            ),
            # bob 可以創建文檔，但有限的操作權限
            ACLPermission(
                subject="bob",
                object="document",
                action=ResourceAction.create | ResourceAction.read,
                effect=PermissionResult.allow,
            ),
            # carol (編輯者) 可以查看和更新所有文檔
            ACLPermission(
                subject="carol",
                object="document",
                action=ResourceAction.read
                | ResourceAction.update
                | ResourceAction.read_list,
                effect=PermissionResult.allow,
            ),
            # david (管理員) 擁有所有權限
            ACLPermission(
                subject="david",
                object="document",
                action=ResourceAction.full,
                effect=PermissionResult.allow,
            ),
        ]

        for acl in acl_permissions:
            permission_checker.resource_manager.create(acl)


def demo_usage():
    """示範如何使用"""
    # 設定系統
    document_manager, permission_checker = setup_document_permission_system()
    setup_initial_permissions(permission_checker)

    # 示範操作
    current_time = dt.datetime.now()

    # 1. alice 創建文檔
    try:
        with document_manager.meta_provide("alice", current_time):
            doc = Document(title="Alice 的文檔", content="這是內容", status="draft")
            doc_info = document_manager.create(doc)
            print(f"Alice 創建文檔: {doc_info.resource_id}")
            doc_id = doc_info.resource_id
    except Exception as e:
        print(f"Alice 創建失敗: {e}")
        return

    # 2. alice 更新自己的文檔（應該成功）
    try:
        with document_manager.meta_provide("alice", current_time):
            updated_doc = Document(
                title="Alice 的更新文檔",
                content="更新的內容",
                status="draft",
            )
            document_manager.update(doc_id, updated_doc)
            print("Alice 成功更新文檔")
    except Exception as e:
        print(f"Alice 更新失敗: {e}")

    # 3. bob 嘗試更新 alice 的文檔（應該失敗）
    try:
        with document_manager.meta_provide("bob", current_time):
            updated_doc = Document(
                title="Bob 嘗試修改",
                content="Bob 的修改",
                status="draft",
            )
            document_manager.update(doc_id, updated_doc)
            print("Bob 成功更新文檔")  # 不應該到這裡
    except Exception as e:
        print(f"Bob 更新失敗（預期）: {e}")

    # 4. carol (editor) 嘗試發布文檔（應該成功，如果不是週末）
    try:
        with document_manager.meta_provide("carol", current_time):
            published_doc = Document(
                title="Alice 的文檔",
                content="這是內容",
                status="published",  # 編輯者可以發布
            )
            document_manager.update(doc_id, published_doc)
            print("Editor 成功發布文檔")
    except Exception as e:
        print(f"Editor 發布失敗: {e}")

    # 5. david (admin) 嘗試刪除文檔（應該成功）
    try:
        with document_manager.meta_provide("david", current_time):
            document_manager.delete(doc_id)
            print("Admin 成功刪除文檔")
    except Exception as e:
        print(f"Admin 刪除失敗: {e}")


if __name__ == "__main__":
    print("🔐 完整權限系統示例")
    print("展示複合權限檢查器的使用")
    print("=" * 50)
    demo_usage()
