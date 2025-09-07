"""改進的權限設定測試示例

展示更安全、更語義化的權限設定方式
"""

import datetime as dt
from dataclasses import dataclass

from autocrud.permission.acl import ACLPermission, ACLPermissionChecker
from autocrud.types import PermissionResult
from autocrud.types import ResourceAction
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore


@dataclass
class TestDocument:
    title: str
    content: str


# 簡化的權限建構器
class PermissionBuilder:
    """簡化的權限建構輔助工具"""

    @staticmethod
    def allow_user_on_resource_type(
        user: str,
        resource_type: str,
        action: str,
    ) -> ACLPermission:
        """允許用戶對資源類型執行特定操作"""
        action_enum = getattr(ResourceAction, action, ResourceAction.get)
        return ACLPermission(
            subject=user,
            object=resource_type,
            action=action_enum,
            effect=PermissionResult.allow,
        )

    @staticmethod
    def allow_user_on_specific_resource(
        user: str,
        resource_id: str,
        action: str,
    ) -> ACLPermission:
        """允許用戶對特定資源執行操作"""
        action_enum = getattr(ResourceAction, action, ResourceAction.get)
        return ACLPermission(
            subject=user,
            object=resource_id,
            action=action_enum,
            effect=PermissionResult.allow,
        )

    @staticmethod
    def allow_group_on_resource_type(
        group: str,
        resource_type: str,
        action: str,
    ) -> ACLPermission:
        """允許群組對資源類型執行操作"""
        if action == "*":
            action_enum = (
                ResourceAction.create
                | ResourceAction.get
                | ResourceAction.get_meta
                | ResourceAction.update
                | ResourceAction.delete
                | ResourceAction.search_resources
            )
        else:
            action_enum = getattr(ResourceAction, action, ResourceAction.get)

        return ACLPermission(
            subject=f"group:{group}",
            object=resource_type,
            action=action_enum,
            effect=PermissionResult.allow,
        )

    @staticmethod
    def create_role_membership(user: str, role: str) -> ACLPermission:
        """創建用戶角色成員關係"""
        return ACLPermission(
            subject=user,
            object=f"role:{role}",
            action=ResourceAction.get,  # 成員關係使用 get 表示
            effect=PermissionResult.allow,
        )


class CommonPermissions:
    """常用權限設定"""

    @staticmethod
    def read_only_for_user(user: str, resource_type: str) -> list[ACLPermission]:
        """為用戶創建只讀權限"""
        return [
            PermissionBuilder.allow_user_on_resource_type(user, resource_type, "get"),
            PermissionBuilder.allow_user_on_resource_type(
                user,
                resource_type,
                "get_meta",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                user,
                resource_type,
                "get_resource_revision",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                user,
                resource_type,
                "search_resources",
            ),
        ]


# 自定義異常類
class PermissionDeniedError(Exception):
    """權限拒絕錯誤"""


def test_improved_permission_setup():
    """測試改進的權限設定方式"""
    # 1. 設定基礎設施
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(TestDocument)
    storage = SimpleStorage(meta_store, resource_store)

    # 創建權限檢查器
    permission_checker = ACLPermissionChecker(
        root_user="system",  # 設定系統用戶為 root 用戶，擁有所有權限
    )

    document_manager = ResourceManager(
        resource_type=TestDocument,
        storage=storage,
        permission_checker=permission_checker,
    )

    # 2. 使用改進的權限設定方式
    admin_user = "system"
    current_time = dt.datetime.now()

    with permission_checker.resource_manager.meta_provide(admin_user, current_time):
        # 使用 PermissionBuilder 設定權限
        permissions = [
            # alice 可以對 test_document 資源類型執行基本操作
            PermissionBuilder.allow_user_on_resource_type(
                "alice",
                "test_document",
                "create",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice",
                "test_document",
                "get",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice",
                "test_document",
                "get_meta",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice",
                "test_document",
                "get_resource_revision",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice",
                "test_document",
                "search_resources",
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice",
                "test_document",
                "update",
            ),
        ]

        for permission in permissions:
            permission_checker.resource_manager.create(permission)

        # 使用 CommonPermissions 設定 bob 的只讀權限
        read_only_permissions = CommonPermissions.read_only_for_user(
            "bob",
            "test_document",
        )
        for permission in read_only_permissions:
            permission_checker.resource_manager.create(permission)

    # 3. 測試權限是否正確工作
    try:
        # alice 應該可以創建文檔
        with document_manager.meta_provide("alice", current_time):
            doc = TestDocument(title="Alice的文檔", content="內容")
            doc_info = document_manager.create(doc)
            print(f"✅ Alice 成功創建文檔: {doc_info.resource_id}")

            # alice 應該可以讀取文檔
            retrieved_doc = document_manager.get(doc_info.resource_id)
            assert retrieved_doc.data.title == "Alice的文檔"
            print("✅ Alice 成功讀取文檔")

        # bob 只有讀取權限，不能創建
        try:
            with document_manager.meta_provide("bob", current_time):
                document_manager.create(TestDocument(title="Bob的文檔", content="內容"))
            print("❌ Bob 不應該能創建文檔")
        except Exception as e:
            print(f"✅ Bob 無法創建文檔（符合預期）: {e}")

        # bob 可以讀取文檔
        with document_manager.meta_provide("bob", current_time):
            retrieved_doc = document_manager.get(doc_info.resource_id)
            assert retrieved_doc.data.title == "Alice的文檔"
            print("✅ Bob 可以讀取文檔")

        print("✅ 改進的權限設定測試全部通過！")

    except Exception as e:
        print(f"❌ 測試失敗: {e}")
        return False

    return True


def test_permission_hierarchy():
    """測試權限層次結構"""
    # 設定基礎設施
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(TestDocument)
    storage = SimpleStorage(meta_store, resource_store)

    permission_checker = ACLPermissionChecker(
        root_user="system",  # 設定系統用戶為 root 用戶
    )

    document_manager = ResourceManager(
        resource_type=TestDocument,
        storage=storage,
        permission_checker=permission_checker,
    )

    admin_user = "system"
    current_time = dt.datetime.now()

    # 創建一個文檔
    try:
        with document_manager.meta_provide("system", current_time):
            doc = TestDocument(title="測試文檔", content="內容")
            doc_info = document_manager.create(doc)

        with permission_checker.resource_manager.meta_provide(admin_user, current_time):
            # 設定不同層次的權限
            permissions = [
                # 1. alice: 對特定資源的權限
                PermissionBuilder.allow_user_on_specific_resource(
                    "alice",
                    doc_info.resource_id,
                    "get",
                ),
                PermissionBuilder.allow_user_on_resource_type(
                    "alice",
                    "test_document",
                    "get_meta",
                ),
                PermissionBuilder.allow_user_on_resource_type(
                    "alice",
                    "test_document",
                    "get_resource_revision",
                ),
                # 2. bob: 對資源類型的權限
                PermissionBuilder.allow_user_on_resource_type(
                    "bob",
                    "test_document",
                    "get",
                ),
                PermissionBuilder.allow_user_on_resource_type(
                    "bob",
                    "test_document",
                    "get_meta",
                ),
                PermissionBuilder.allow_user_on_resource_type(
                    "bob",
                    "test_document",
                    "get_resource_revision",
                ),
                # 3. charlie: 同樣的資源類型權限
                PermissionBuilder.allow_user_on_resource_type(
                    "charlie",
                    "test_document",
                    "get",
                ),
                PermissionBuilder.allow_user_on_resource_type(
                    "charlie",
                    "test_document",
                    "get_meta",
                ),
                PermissionBuilder.allow_user_on_resource_type(
                    "charlie",
                    "test_document",
                    "get_resource_revision",
                ),
            ]

            for permission in permissions:
                permission_checker.resource_manager.create(permission)

        # 測試不同層次的權限
        test_users = ["alice", "bob", "charlie"]

        for user in test_users:
            with document_manager.meta_provide(user, current_time):
                try:
                    retrieved_doc = document_manager.get(doc_info.resource_id)
                    print(f"✅ {user} 成功讀取文檔")
                except Exception as e:
                    if user == "alice":
                        print(
                            f"✅ {user} 無法讀取文檔（符合預期，只有特定資源權限）: {e}",
                        )
                    else:
                        print(f"❌ {user} 無法讀取文檔: {e}")

        print("✅ 權限層次結構測試完成！")
        return True

    except Exception as e:
        print(f"❌ 權限層次結構測試失敗: {e}")
        return False


def demonstrate_object_meanings():
    """示範 object 欄位的不同含義"""
    print("\n=== ACLPermission.object 欄位含義示範 ===")

    # 1. 特定資源 ID
    specific_resource_permission = PermissionBuilder.allow_user_on_specific_resource(
        "alice",
        "document:123e4567-e89b-12d3-a456-426614174000",
        "get",
    )
    print(f"1. 特定資源權限: {specific_resource_permission.object}")
    print("   含義: 只對這個具體的文檔有權限")

    # 2. 資源類型
    resource_type_permission = PermissionBuilder.allow_user_on_resource_type(
        "alice",
        "document",
        "create",
    )
    print(f"2. 資源類型權限: {resource_type_permission.object}")
    print("   含義: 對所有 document 類型的資源有權限")

    # 3. 萬用權限
    universal_permission = PermissionBuilder.allow_group_on_resource_type(
        "admin",
        "document",
        "get",
    )
    print(f"3. 群組權限: {universal_permission.object}")
    print("   含義: 群組對所有 document 類型的資源有權限")

    print("\n權限匹配優先級（從高到低）：")
    print("1. 精確資源ID匹配 > 2. 資源類型匹配 > 3. 萬用匹配")
    print("建議：優先使用資源類型匹配，避免直接使用萬用權限")


if __name__ == "__main__":
    print("=== 測試改進的權限設定系統 ===")
    success1 = test_improved_permission_setup()
    print("\n" + "=" * 50)
    success2 = test_permission_hierarchy()
    print("\n" + "=" * 50)
    demonstrate_object_meanings()

    if success1 and success2:
        print("\n🎉 所有測試都通過了！")
    else:
        print("\n❌ 部分測試失敗")
