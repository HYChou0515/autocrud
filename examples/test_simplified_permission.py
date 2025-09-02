#!/usr/bin/env python3
"""簡化的權限測試"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from dataclasses import dataclass
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.resource_manager.permission import PermissionResourceManager
from autocrud.resource_manager.permission_utils import PermissionBuilder


@dataclass
class TestDocument:
    title: str
    content: str


def test_simplified():
    """簡化的權限測試"""

    print("=== 簡化權限測試 ===")

    # 設定基本組件
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore(TestDocument)
    storage = SimpleStorage(meta_store=meta_store, resource_store=resource_store)

    # 設定權限管理器
    permission_resource_store = MemoryResourceStore(dict)
    permission_storage = SimpleStorage(
        meta_store=meta_store, resource_store=permission_resource_store
    )
    permission_manager = PermissionResourceManager(storage=permission_storage)

    # 建立 document manager
    document_manager = ResourceManager(
        TestDocument, storage=storage, permission_manager=permission_manager
    )
    current_time = datetime.now()

    # 設定權限
    print("\n=== 設定權限 ===")
    builder = PermissionBuilder()
    builder.meta_store = meta_store

    # 給 alice 權限 - 需要手動保存到權限管理器
    permission = builder.allow_user_on_resource_type(
        "alice", "test_document", ["create", "read"]
    )
    print(f"創建了權限: {permission}")

    # 手動保存權限到權限管理器
    current_time = datetime.now()
    with permission_manager.meta_provide("system", current_time):
        permission_info = permission_manager.create(permission)
        print(f"保存權限: {permission_info.resource_id}")

    # 檢查實際存儲的權限數據
    print("\n=== 檢查存儲的權限 ===")
    print(f"Meta store 中總項目數: {len(meta_store)}")

    for key in meta_store:
        meta = meta_store[key]
        print(f"Key: {key}")
        print(f"  Indexed data: {meta.indexed_data}")
        if "type" in meta.indexed_data:
            print(f"  Type value: '{meta.indexed_data['type']}'")
        if "action" in meta.indexed_data:
            print(
                f"  Action value: {meta.indexed_data['action']} (type: {type(meta.indexed_data['action'])})"
            )

    # 測試權限檢查
    print("\n=== 測試權限檢查 ===")
    with permission_manager.meta_provide("user:alice", current_time):
        can_create = permission_manager.check_permission(
            "user:alice", "create", "test_document"
        )
        print(f"Alice 可以 create test_document: {can_create}")

        # 嘗試實際創建
        print("\n=== 測試實際創建 ===")
        try:
            with document_manager.meta_provide("user:alice", current_time):
                doc = TestDocument(title="測試文檔", content="測試內容")
                doc_info = document_manager.create(doc)
                print(f"✅ 成功創建文檔: {doc_info.resource_id}")
        except Exception as e:
            print(f"❌ 創建失敗: {e}")


if __name__ == "__main__":
    test_simplified()
