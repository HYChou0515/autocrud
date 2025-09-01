#!/usr/bin/env python3
"""調試權限問題"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    context = PermissionContext(
        user="user:alice",
        action="create",
        resource_name="test_document",
        resource_id=None,
        method="POST",
        path="/test_document",
        request_data={"title": "test", "content": "test"}
    )
    
    # 需要在權限管理器的用戶 context 中進行測試
    with permission_manager.meta_provide("user:alice", current_time):
        checker = DefaultPermissionChecker(permission_manager)
        result = checker.check_permission(context)
        print(f"Context 檢查結果: {result}")path.abspath(__file__))))

from datetime import datetime
from dataclasses import dataclass
from autocrud.resource_manager.core import ResourceManager
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore  
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.core import SimpleStorage
from autocrud.resource_manager.permission_context import (
    PermissionContext, DefaultPermissionChecker, CompositePermissionChecker
)
from autocrud.resource_manager.permission import PermissionResourceManager
from autocrud.resource_manager.permission_utils import PermissionBuilder

@dataclass
class TestDocument:
    title: str
    content: str

def debug_permission_issue():
    """調試權限問題"""
    
    print("=== 調試權限問題 ===")
    
    # 設定基本設置
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(TestDocument)
    
    storage = SimpleStorage(
        meta_store=meta_store,
        resource_store=resource_store,
    )
    
    # 設定權限管理器需要單獨的 storage
    permission_resource_store = MemoryResourceStore(dict)  # permissions 是 dict
    permission_storage = SimpleStorage(
        meta_store=meta_store,
        resource_store=permission_resource_store,
    )
    permission_manager = PermissionResourceManager(storage=permission_storage)
    
    # 建立 document manager
    document_manager = ResourceManager(
        TestDocument,
        storage=storage,
        permission_manager=permission_manager
    )
    
    permission_manager = document_manager.permission_manager
    current_time = datetime.now()
    
    # 設定權限 - 使用安全的 PermissionBuilder
    builder = PermissionBuilder()
    builder.meta_store = meta_store  # 手動設置 meta_store
    
    # 給 alice 在 test_document 資源類型上的完整權限
    # 注意：PermissionBuilder 只創建權限對象，需要手動保存
    for action in ["create", "read", "update", "delete"]:
        permission = builder.allow_user_on_resource_type("alice", "test_document", action)
        # 保存權限到權限管理器
        with permission_manager.meta_provide("system", current_time):
            perm_info = permission_manager.create(permission)
            print(f"創建權限: {action} -> {perm_info.resource_id}")
    
    print(f"Meta store 中項目數: {len(meta_store)}")
    
    # 檢查所有現有權限 - 簡化版本
    print("\n=== 檢查權限 ===")
    print(f"權限管理器類型: {type(permission_manager)}")
    print(f"Meta store 中總項目數: {len(meta_store)}")
    
    # 直接列出 meta_store 中的所有項目
    for key in meta_store:
        meta = meta_store[key]
        print(f"Key: {key}, Type: {type(meta)}, Data: {meta}")
        if hasattr(meta, 'data') and isinstance(meta.data, dict):
            print(f"  Data type: {meta.data.get('type', 'unknown')}")
            if meta.data.get('type') == 'acl_permission':
                print(f"  ACL Permission: {meta.data}")
    
    # 測試權限檢查
    print("\n=== 測試權限檢查 ===")
    
    # 需要在權限管理器的用戶 context 中進行權限檢查
    with permission_manager.meta_provide("user:alice", current_time):
        alice_can_create = permission_manager.check_permission("user:alice", "create", "test_document")
        print(f"Alice 可以 create test_document: {alice_can_create}")
        
        alice_can_create_wildcard = permission_manager.check_permission("user:alice", "create", "*")
        print(f"Alice 可以 create *: {alice_can_create_wildcard}")
        
        alice_can_create_none = permission_manager.check_permission("user:alice", "create", None)
        print(f"Alice 可以 create None: {alice_can_create_none}")
    
    # 測試 context 系統
    context = PermissionContext(
        user="user:alice",
        action="create",
        resource_name="test_document",
        resource_id=None,
        method_name="create",
        method_kwargs={"data": {"title": "test", "content": "test"}}
    )
    
    checker = DefaultPermissionChecker(permission_manager)
    result = checker.check_permission(context)
    print(f"Context 檢查結果: {result}")
    
    # 嘗試實際創建
    print("\n=== 嘗試創建資源 ===")
    try:
        with document_manager.meta_provide("user:alice", current_time):
            doc = TestDocument(title="測試文檔", content="測試內容")
            doc_info = document_manager.create(doc)
            print(f"✅ 成功創建文檔: {doc_info.resource_id}")
    except Exception as e:
        print(f"❌ 創建失敗: {e}")
        print(f"錯誤類型: {type(e)}")

if __name__ == "__main__":
    debug_permission_issue()
