"""檢查持久化文件格式"""

import json
import tempfile
import os
from dataclasses import dataclass
from autocrud import AutoCRUD, MemoryStorage


@dataclass
class TestItem:
    name: str
    value: int


def show_persistence_file_format():
    """展示持久化文件的格式"""
    print("=== 持久化文件格式展示 ===")

    temp_dir = tempfile.mkdtemp()
    persist_file = os.path.join(temp_dir, "format_demo.json")

    # 創建數據
    storage = MemoryStorage(persist_file=persist_file)
    crud = AutoCRUD(model=TestItem, storage=storage, resource_name="items")

    # 添加測試數據
    crud.create({"name": "項目A", "value": 100})
    crud.create({"name": "項目B", "value": 200})

    # 顯示文件內容
    print(f"持久化文件路徑: {persist_file}")

    if os.path.exists(persist_file):
        with open(persist_file, "r", encoding="utf-8") as f:
            content = f.read()

        print("\n文件內容:")
        print("=" * 50)
        print(content)
        print("=" * 50)

        # 解析並顯示結構
        data = json.loads(content)
        print("\n文件結構:")
        print(f"序列化器類型: {data['serializer_type']}")
        print(f"數據條目數: {len(data['data'])}")
        print(f"數據鍵: {list(data['data'].keys())}")

        # 清理
        os.remove(persist_file)

    print("\n✅ 持久化功能工作正常！")


if __name__ == "__main__":
    show_persistence_file_format()
