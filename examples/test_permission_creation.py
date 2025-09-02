#!/usr/bin/env python3
"""測試權限的創建和搜索"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.permission_utils import PermissionBuilder


def test_permission_creation():
    """測試權限創建和存儲"""

    print("=== 測試權限創建 ===")

    # 設定基本組件
    meta_store = MemoryMetaStore()

    # 設定權限
    builder = PermissionBuilder()
    builder.meta_store = meta_store

    # 創建權限
    permission = builder.allow_user_on_resource_type(
        "alice", "test_document", ["create", "read"]
    )
    print(f"創建的權限: {permission}")
    print(f"權限類型: {type(permission)}")
    print(f"Subject: {permission.subject}")
    print(f"Object: {permission.object}")
    print(f"Action: {permission.action}")
    print(f"Action 類型: {type(permission.action)}")

    # 檢查 meta_store 中的數據
    print("\n=== Meta Store 內容 ===")
    print(f"Meta store 中總項目數: {len(meta_store)}")

    for key in meta_store:
        meta = meta_store[key]
        print(f"Key: {key}")
        print(f"  Type: {type(meta)}")
        print(f"  Indexed data: {meta.indexed_data}")
        if "action" in meta.indexed_data:
            action_value = meta.indexed_data["action"]
            print(f"  Action value: {action_value}")
            print(f"  Action type: {type(action_value)}")


if __name__ == "__main__":
    test_permission_creation()
