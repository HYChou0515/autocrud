"""
簡單的權限設定測試
"""

import pytest
import datetime as dt
from dataclasses import dataclass

from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.permission import PermissionResourceManager, ACLPermission, Effect, Permission
from autocrud.resource_manager.permission_context import DefaultPermissionChecker
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore


@dataclass
class TestDocument:
    title: str
    content: str


def test_basic_permission_setup():
    """測試基本權限設定"""
    
    # 1. 創建儲存
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(resource_type=TestDocument)
    storage = SimpleStorage(meta_store, resource_store)
    
    # 2. 創建權限管理器
    permission_meta_store = MemoryMetaStore()
    permission_resource_store = MemoryResourceStore(resource_type=Permission)
    permission_storage = SimpleStorage(permission_meta_store, permission_resource_store)
    permission_manager = PermissionResourceManager(Permission, storage=permission_storage)
    
    # 3. 創建權限檢查器
    permission_checker = DefaultPermissionChecker(permission_manager)
    
    # 4. 創建文檔管理器並設定權限檢查器
    document_manager = ResourceManager(
        resource_type=TestDocument,
        storage=storage,
        permission_checker=permission_checker  # 關鍵：設定權限檢查器
    )
    
    # 5. 設定一些基本權限
    admin_user = "admin"
    test_user = "user:alice"
    current_time = dt.datetime.now()
    
    with permission_manager.meta_provide(admin_user, current_time):
        # 給 alice 創建文檔的權限
        create_permission = ACLPermission(
            subject=test_user,
            object="test_document",  # 對應 resource_name
            action="create",
            effect=Effect.allow
        )
        permission_manager.create(create_permission)
        
        # 給 alice 讀取權限 - 使用 None 表示任何資源
        read_permission = ACLPermission(
            subject=test_user,
            object=None,  # None 表示任何資源
            action="get", 
            effect=Effect.allow
        )
        permission_manager.create(read_permission)
    
    # 6. 測試權限是否生效
    
    # alice 應該可以創建文檔
    with document_manager.meta_provide(test_user, current_time):
        doc = TestDocument(title="測試文檔", content="測試內容")
        doc_info = document_manager.create(doc)
        print(f"Alice 創建文檔: {doc_info.resource_id}")
        
        # 為這個具體的資源 ID 添加所有讀取相關權限
        with permission_manager.meta_provide(admin_user, current_time):
            read_actions = ["get", "get_meta", "get_resource_revision"]
            for action in read_actions:
                permission = ACLPermission(
                    subject=test_user,
                    object=doc_info.resource_id,  # 具體的資源 ID
                    action=action,
                    effect=Effect.allow
                )
                permission_manager.create(permission)
        
        # alice 應該可以讀取文檔
        retrieved_doc = document_manager.get(doc_info.resource_id)
        assert retrieved_doc.data.title == "測試文檔"
    
    # 沒有權限的用戶應該無法操作
    unauthorized_user = "user:bob"
    
    with pytest.raises(Exception):  # 應該拋出權限錯誤
        with document_manager.meta_provide(unauthorized_user, current_time):
            document_manager.create(TestDocument(title="Bob的文檔", content="內容"))
    
    print("✅ 基本權限設定測試通過！")


if __name__ == "__main__":
    test_basic_permission_setup()
