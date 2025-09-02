"""
改進的權限設定測試示例

展示更安全、更語義化的權限設定方式
"""

import pytest
import datetime as dt
from dataclasses import dataclass

from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.permission import (
    PermissionResourceManager,
    Permission,
)
from autocrud.resource_manager.permission_context import DefaultPermissionChecker
from autocrud.resource_manager.permission_utils import (
    PermissionBuilder,
    CommonPermissions,
)
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.basic import PermissionDeniedError


@dataclass
class TestDocument:
    title: str
    content: str


def test_improved_permission_setup():
    """測試改進的權限設定方式"""

    # 1. 設定基礎設施
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(resource_type=TestDocument)
    storage = SimpleStorage(meta_store, resource_store)

    permission_meta_store = MemoryMetaStore()
    permission_resource_store = MemoryResourceStore(resource_type=Permission)
    permission_storage = SimpleStorage(permission_meta_store, permission_resource_store)
    permission_manager = PermissionResourceManager(
        Permission, storage=permission_storage
    )

    permission_checker = DefaultPermissionChecker(permission_manager)

    document_manager = ResourceManager(
        resource_type=TestDocument,
        storage=storage,
        permission_checker=permission_checker,
    )

    # 2. 使用改進的權限設定方式
    admin_user = "admin"
    current_time = dt.datetime.now()

    with permission_manager.meta_provide(admin_user, current_time):
        # 方法 1: 使用 PermissionBuilder (推薦)
        permissions = [
            # alice 可以對 test_document 資源類型執行基本操作
            PermissionBuilder.allow_user_on_resource_type(
                "alice", "test_document", "create"
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice", "test_document", "get"
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice", "test_document", "get_meta"
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice", "test_document", "get_resource_revision"
            ),
            PermissionBuilder.allow_user_on_resource_type(
                "alice", "test_document", "search_resources"
            ),
            # admin 群組擁有所有權限
            PermissionBuilder.allow_group_on_resource_type("admin", "*", "*"),
            # 創建角色關係
            PermissionBuilder.create_role_membership("alice", "editor"),
        ]

        for permission in permissions:
            permission_manager.create(permission)

        # 方法 2: 使用 CommonPermissions (更便利)
        read_only_permissions = CommonPermissions.read_only_for_user(
            "bob", "test_document"
        )
        for permission in read_only_permissions:
            permission_manager.create(permission)

    # 3. 測試權限是否正確工作

    # alice 應該可以創建文檔
    with document_manager.meta_provide("user:alice", current_time):
        doc = TestDocument(title="Alice的文檔", content="內容")
        doc_info = document_manager.create(doc)
        print(f"✅ Alice 成功創建文檔: {doc_info.resource_id}")

        # alice 應該可以讀取文檔
        retrieved_doc = document_manager.get(doc_info.resource_id)
        assert retrieved_doc.data.title == "Alice的文檔"
        print("✅ Alice 成功讀取文檔")

    # bob 只有讀取權限，不能創建
    with pytest.raises(PermissionDeniedError):
        with document_manager.meta_provide("user:bob", current_time):
            document_manager.create(TestDocument(title="Bob的文檔", content="內容"))
    print("✅ Bob 無法創建文檔（符合預期）")

    # bob 可以讀取文檔
    with document_manager.meta_provide("user:bob", current_time):
        retrieved_doc = document_manager.get(doc_info.resource_id)
        assert retrieved_doc.data.title == "Alice的文檔"
        print("✅ Bob 可以讀取文檔")

    print("✅ 改進的權限設定測試全部通過！")


def test_permission_hierarchy():
    """測試權限層次結構"""

    # 設定基礎設施
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(resource_type=TestDocument)
    storage = SimpleStorage(meta_store, resource_store)

    permission_meta_store = MemoryMetaStore()
    permission_resource_store = MemoryResourceStore(resource_type=Permission)
    permission_storage = SimpleStorage(permission_meta_store, permission_resource_store)
    permission_manager = PermissionResourceManager(
        Permission, storage=permission_storage
    )

    permission_checker = DefaultPermissionChecker(permission_manager)

    document_manager = ResourceManager(
        resource_type=TestDocument,
        storage=storage,
        permission_checker=permission_checker,
    )

    admin_user = "admin"
    current_time = dt.datetime.now()

    # 創建一個文檔
    with document_manager.meta_provide("system", current_time):
        doc = TestDocument(title="測試文檔", content="內容")
        doc_info = document_manager.create(doc)

    with permission_manager.meta_provide(admin_user, current_time):
        # 設定不同層次的權限
        permissions = [
            # 1. 最具體：對特定資源的權限
            PermissionBuilder.allow_user_on_specific_resource(
                "alice", doc_info.resource_id, "get"
            ),
            # 2. 中等：對資源類型的權限
            PermissionBuilder.allow_user_on_resource_type(
                "bob", "test_document", "get"
            ),
            # 3. 最廣泛：萬用權限 (謹慎使用)
            PermissionBuilder.allow_user_on_resource_type("charlie", "*", "get"),
        ]

        for permission in permissions:
            permission_manager.create(permission)

    # 測試不同層次的權限
    test_users = ["user:alice", "user:bob", "user:charlie"]

    for user in test_users:
        with document_manager.meta_provide(user, current_time):
            try:
                retrieved_doc = document_manager.get(doc_info.resource_id)
                print(f"✅ {user} 成功讀取文檔")
            except PermissionDeniedError:
                print(f"❌ {user} 無法讀取文檔")

    print("✅ 權限層次結構測試完成！")


def demonstrate_object_meanings():
    """示範 object 欄位的不同含義"""

    print("\n=== ACLPermission.object 欄位含義示範 ===")

    # 1. 特定資源 ID
    specific_resource_permission = PermissionBuilder.allow_user_on_specific_resource(
        "alice", "document:123e4567-e89b-12d3-a456-426614174000", "get"
    )
    print(f"1. 特定資源權限: {specific_resource_permission.object}")
    print("   含義: 只對這個具體的文檔有權限")

    # 2. 資源類型
    resource_type_permission = PermissionBuilder.allow_user_on_resource_type(
        "alice", "document", "create"
    )
    print(f"2. 資源類型權限: {resource_type_permission.object}")
    print("   含義: 對所有 document 類型的資源有權限")

    # 3. 萬用權限
    universal_permission = PermissionBuilder.allow_group_on_resource_type(
        "admin", "*", "*"
    )
    print(f"3. 萬用權限: {universal_permission.object}")
    print("   含義: 對所有類型的資源有權限（需謹慎使用）")

    print("\n權限匹配優先級（從高到低）：")
    print("1. 精確資源ID匹配 > 2. 資源類型匹配 > 3. 萬用匹配")
    print("建議：優先使用資源類型匹配，避免直接使用萬用權限")


if __name__ == "__main__":
    print("=== 測試改進的權限設定系統 ===")
    test_improved_permission_setup()
    print("\n" + "=" * 50)
    test_permission_hierarchy()
    print("\n" + "=" * 50)
    demonstrate_object_meanings()
