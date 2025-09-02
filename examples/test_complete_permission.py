#!/usr/bin/env python3
"""完整的權限系統測試"""


from datetime import datetime
from dataclasses import dataclass
from autocrud.resource_manager.basic import ResourceAction
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore  
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.permission import PermissionResourceManager
from autocrud.resource_manager.permission import ACLPermission

@dataclass
class TestDocument:
    title: str
    content: str

def test_complete_permission_system():
    """完整的權限系統測試"""
    
    print("=== 完整權限系統測試 ===")
    
    # 設定基本組件
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(TestDocument)
    storage = SimpleStorage(meta_store=meta_store, resource_store=resource_store)
    
    # 設定權限管理器
    permission_resource_store = MemoryResourceStore(dict)
    permission_storage = SimpleStorage(meta_store=meta_store, resource_store=permission_resource_store)
    permission_manager = PermissionResourceManager(storage=permission_storage, name="permission")
    
    # 建立 document manager
    document_manager = ResourceManager(TestDocument, storage=storage, permission_manager=permission_manager)
    current_time = datetime.now()
    
    # 設定權限
    print("\n=== 設定權限 ===")
    
    # 給 alice 創建和讀取權限
    alice_permissions = ACLPermission(
        subject="alice",
        object="test_document",
        action=ResourceAction.write | ResourceAction.read,
    )
    
    # 在 system context 中創建權限
    with permission_manager.meta_provide("system", current_time):
        alice_resource_id = permission_manager.create(alice_permissions).resource_id
        print(f"Alice 權限: {alice_resource_id}")
        
        # 給 bob 只有讀取權限
        bob_permissions = ACLPermission(
            subject="bob",
            object="test_document",
            action=ResourceAction.read,
        )
        bob_resource_id = permission_manager.create(bob_permissions).resource_id
        print(f"Bob 權限: {bob_resource_id}")
    
    print(f"\n權限管理器中總權限數: {len(meta_store)}")
    
    # 測試 alice 的權限
    print("\n=== 測試 Alice 權限 ===")
    with permission_manager.meta_provide("alice", current_time):
        alice_can_create = permission_manager.check_permission("alice", ResourceAction.create, "test_document")
        alice_can_read = permission_manager.check_permission("alice", ResourceAction.read, "test_document")
        alice_can_update = permission_manager.check_permission("alice", ResourceAction.update, "test_document")
        
        print(f"Alice 可以 create: {alice_can_create}")
        print(f"Alice 可以 read: {alice_can_read}")
        print(f"Alice 可以 update: {alice_can_update}")
    
    # 測試 bob 的權限
    print("\n=== 測試 Bob 權限 ===")
    with permission_manager.meta_provide("bob", current_time):
        bob_can_create = permission_manager.check_permission("bob", ResourceAction.create, "test_document")
        bob_can_read = permission_manager.check_permission("bob", ResourceAction.read, "test_document")
        bob_can_update = permission_manager.check_permission("bob", ResourceAction.update, "test_document")
        
        print(f"Bob 可以 create: {bob_can_create}")
        print(f"Bob 可以 read: {bob_can_read}")
        print(f"Bob 可以 update: {bob_can_update}")
    
    # 測試 root 用戶權限
    print("\n=== 測試 Root 用戶權限 ===")
    with permission_manager.meta_provide("root", current_time):
        root_can_create = permission_manager.check_permission("root", ResourceAction.create, "test_document")
        root_can_read = permission_manager.check_permission("root", ResourceAction.read, "test_document")
        root_can_update = permission_manager.check_permission("root", ResourceAction.update, "test_document")
        root_can_delete = permission_manager.check_permission("root", ResourceAction.delete, "test_document")

        print(f"Root 可以 create: {root_can_create}")
        print(f"Root 可以 read: {root_can_read}")
        print(f"Root 可以 update: {root_can_update}")
        print(f"Root 可以 delete: {root_can_delete}")
    
    # 測試實際操作
    print("\n=== 測試實際操作 ===")
    
    # Alice 創建文檔
    try:
        with document_manager.meta_provide("alice", current_time):
            doc = TestDocument(title="Alice的文檔", content="Alice的內容")
            doc_info = document_manager.create(doc)
            print(f"✅ Alice 成功創建文檔: {doc_info.resource_id}")
            doc_id = doc_info.resource_id
    except Exception as e:
        print(f"❌ Alice 創建失敗: {e}")
        return
    
    # Bob 嘗試創建文檔（應該失敗）
    try:
        with document_manager.meta_provide("bob", current_time):
            doc = TestDocument(title="Bob的文檔", content="Bob的內容")
            doc_info = document_manager.create(doc)
            print(f"❌ Bob 不應該能創建文檔: {doc_info.resource_id}")
    except Exception as e:
        print(f"✅ Bob 創建失敗（符合預期）: {e}")
    
    # Bob 讀取 Alice 的文檔
    try:
        with document_manager.meta_provide("bob", current_time):
            retrieved_doc = document_manager.get(doc_id)
            print(f"✅ Bob 成功讀取文檔: {retrieved_doc.data.title}")
    except Exception as e:
        print(f"❌ Bob 讀取失敗: {e}")
    
    # Root 可以做任何事
    try:
        with document_manager.meta_provide("root", current_time):
            # Root 創建文檔
            root_doc = TestDocument(title="Root的文檔", content="Root的內容")
            root_doc_info = document_manager.create(root_doc)
            print(f"✅ Root 成功創建文檔: {root_doc_info.resource_id}")
            
            # Root 讀取任何文檔
            retrieved_doc = document_manager.get(doc_id)
            print(f"✅ Root 成功讀取 Alice 的文檔: {retrieved_doc.data.title}")
    except Exception as e:
        print(f"❌ Root 操作失敗: {e}")
    
    print("\n=== 權限系統測試完成 ===")

if __name__ == "__main__":
    test_complete_permission_system()
