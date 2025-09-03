"""
完整的權限設定和使用示例
"""

import datetime as dt
from dataclasses import dataclass
from autocrud.permission.acl import ACLPermissionChecker
from autocrud.permission.basic import PermissionContext, PermissionResult
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.permission import (
    PermissionResourceManager,
    ACLPermission,
    RoleMembership,
    Effect,
)
from autocrud.resource_manager.permission_context import (
    FieldLevelPermissionChecker,
    ResourceOwnershipChecker,
    ConditionalPermissionChecker,
    CompositePermissionChecker,
    PermissionChecker,
)
from autocrud.resource_manager.resource_store.simple import SimpleResourceStore
from autocrud.resource_manager.meta_store.simple import SimpleMetaStore


# 示例資料結構
@dataclass
class Document:
    title: str
    content: str
    status: str = "draft"  # draft, published, archived
    category: str = "general"


class DocumentPermissionChecker(PermissionChecker):
    """自定義文檔權限檢查器"""

    def check_permission(self, context: PermissionContext) -> PermissionResult:
        """實現文檔特定的權限邏輯"""

        # 1. 草稿狀態的文檔只有作者可以查看
        if context.action == "get" and context.resource_data:
            if hasattr(context.resource_data, "status"):
                if context.resource_data.status == "draft":
                    # 需要檢查是否為作者（通過所有權檢查器處理）
                    return PermissionResult.not_applicable

        # 2. 只有編輯者可以發布文檔
        if context.action == "update" and context.method_kwargs.get("data"):
            data = context.method_kwargs["data"]
            if hasattr(data, "status") and data.status == "published":
                if not context.user.startswith(
                    "editor:"
                ) and not context.user.startswith("admin:"):
                    return PermissionResult.deny

        # 3. 歸檔文檔不能修改
        if context.action in {"update", "patch"} and context.resource_data:
            if hasattr(context.resource_data, "status"):
                if context.resource_data.status == "archived":
                    return PermissionResult.deny

        return PermissionResult.not_applicable


def setup_document_permission_system():
    """設定文檔管理的權限系統"""

    # 1. 創建儲存
    resource_store = SimpleResourceStore()
    meta_store = SimpleMetaStore()

    # 2. 創建權限管理器
    permission_manager = PermissionResourceManager(
        storage={"resource_store": resource_store, "meta_store": meta_store}
    )

    # 3. 創建文檔管理器
    document_manager = ResourceManager(
        resource_type=Document,
        storage={"resource_store": resource_store, "meta_store": meta_store},
    )

    # 4. 設定權限檢查器

    # 4.1 欄位級權限
    field_checker = FieldLevelPermissionChecker(
        allowed_fields_by_user={
            "author:alice": {"title", "content"},  # 作者只能修改標題和內容
            "author:bob": {"title", "content"},
            "editor:carol": {
                "title",
                "content",
                "status",
                "category",
            },  # 編輯者可以改狀態
            "admin:david": {"title", "content", "status", "category"},  # 管理員全權限
        }
    )

    # 4.2 資源所有權檢查
    ownership_checker = ResourceOwnershipChecker(
        resource_manager=document_manager,
        allowed_actions={"get", "update", "patch", "delete"},
    )

    # 4.3 條件式檢查
    conditional_checker = ConditionalPermissionChecker()

    # 只有管理員可以刪除
    conditional_checker.add_condition(
        lambda ctx: PermissionResult.deny
        if ctx.action == "delete" and not ctx.user.startswith("admin:")
        else PermissionResult.not_applicable
    )

    # 週末不能發布文檔
    def no_weekend_publish(context):
        if context.action == "update" and context.method_kwargs.get("data"):
            data = context.method_kwargs["data"]
            if hasattr(data, "status") and data.status == "published":
                if dt.datetime.now().weekday() >= 5:  # 週末
                    return PermissionResult.deny
        return PermissionResult.not_applicable

    conditional_checker.add_condition(no_weekend_publish)

    # 4.4 基本 ACL/RBAC 檢查
    acl_checker = ACLPermissionChecker(permission_manager)

    # 4.5 自定義文檔權限檢查
    document_checker = DocumentPermissionChecker()

    # 4.6 組合所有檢查器
    composite_checker = CompositePermissionChecker(
        [
            conditional_checker,  # 最高優先級：條件限制
            document_checker,  # 文檔特定邏輯
            field_checker,  # 欄位權限
            ownership_checker,  # 所有權檢查
            acl_checker,  # 基本 ACL/RBAC
        ]
    )

    # 5. 將權限檢查器設定到文檔管理器
    document_manager.permission_checker = composite_checker

    return document_manager, permission_manager


def setup_initial_permissions(permission_manager):
    """設定初始權限資料"""

    admin_user = "system:admin"
    current_time = dt.datetime.now()

    with permission_manager.meta_provide(admin_user, current_time):
        # 創建角色成員關係
        memberships = [
            RoleMembership(subject="author:alice", group="group:authors"),
            RoleMembership(subject="author:bob", group="group:authors"),
            RoleMembership(subject="editor:carol", group="group:editors"),
            RoleMembership(subject="admin:david", group="group:admins"),
        ]

        for membership in memberships:
            permission_manager.create(membership)

        # 創建 ACL 權限
        acl_permissions = [
            # 作者群組可以創建文檔
            ACLPermission(
                subject="group:authors",
                object="documents",
                action="create",
                effect=Effect.allow,
            ),
            # 編輯者群組可以查看所有文檔
            ACLPermission(
                subject="group:editors",
                object="documents",
                action="get",
                effect=Effect.allow,
            ),
            ACLPermission(
                subject="group:editors",
                object="documents",
                action="search_resources",
                effect=Effect.allow,
            ),
            # 管理員群組擁有所有權限
            ACLPermission(
                subject="group:admins",
                object="documents",
                action="*",  # 萬用字元
                effect=Effect.allow,
            ),
        ]

        for acl in acl_permissions:
            permission_manager.create(acl)


def demo_usage():
    """示範如何使用"""

    # 設定系統
    document_manager, permission_manager = setup_document_permission_system()
    setup_initial_permissions(permission_manager)

    # 示範操作
    current_time = dt.datetime.now()

    # 1. alice 創建文檔
    with document_manager.meta_provide("author:alice", current_time):
        doc = Document(title="Alice 的文檔", content="這是內容", status="draft")
        doc_info = document_manager.create(doc)
        print(f"Alice 創建文檔: {doc_info.resource_id}")

    # 2. alice 更新自己的文檔（應該成功）
    try:
        with document_manager.meta_provide("author:alice", current_time):
            updated_doc = Document(
                title="Alice 的更新文檔", content="更新的內容", status="draft"
            )
            document_manager.update(doc_info.resource_id, updated_doc)
            print("Alice 成功更新文檔")
    except Exception as e:
        print(f"Alice 更新失敗: {e}")

    # 3. bob 嘗試更新 alice 的文檔（應該失敗）
    try:
        with document_manager.meta_provide("author:bob", current_time):
            updated_doc = Document(
                title="Bob 嘗試修改", content="Bob 的修改", status="draft"
            )
            document_manager.update(doc_info.resource_id, updated_doc)
            print("Bob 成功更新文檔")  # 不應該到這裡
    except Exception as e:
        print(f"Bob 更新失敗（預期）: {e}")

    # 4. editor 嘗試發布文檔（應該成功，如果不是週末）
    try:
        with document_manager.meta_provide("editor:carol", current_time):
            published_doc = Document(
                title="Alice 的文檔",
                content="這是內容",
                status="published",  # 編輯者可以發布
            )
            document_manager.update(doc_info.resource_id, published_doc)
            print("Editor 成功發布文檔")
    except Exception as e:
        print(f"Editor 發布失敗: {e}")


if __name__ == "__main__":
    demo_usage()
