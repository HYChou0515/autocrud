#!/usr/bin/env python3
"""
測試 AutoCRUD 的 metadata_config 功能
"""

from autocrud import AutoCRUD
from autocrud.metadata import MetadataConfig
from dataclasses import dataclass
from typing import Optional
import uuid


@dataclass
class User:
    id: str
    name: str
    email: str
    age: Optional[int] = None
    created_time: Optional[str] = None
    updated_time: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    # 添加覆蓋測試需要的字段
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    author: Optional[str] = None
    last_editor: Optional[str] = None


def custom_id_generator():
    """自訂 ID 生成器"""
    return f"user_{uuid.uuid4().hex[:8]}"


def get_current_user():
    """模擬取得當前使用者"""
    return "admin"


def test_autocrud_with_default_metadata_config():
    """測試在 AutoCRUD 初始化時設定預設 metadata config"""

    print("=== 測試 AutoCRUD 預設 metadata config ===")

    # 建立 metadata config
    metadata_config = MetadataConfig.with_full_tracking(
        created_time_field="created_time",
        updated_time_field="updated_time",
        created_by_field="created_by",
        updated_by_field="updated_by",
        get_current_user=get_current_user,
    )

    # 建立 AutoCRUD 並設定預設配置
    autocrud = AutoCRUD(
        metadata_config=metadata_config,
        id_generator=custom_id_generator,
        use_plural=True,
    )

    # 註冊模型（使用預設配置）
    autocrud.register_model(User)

    # 創建資料
    user_id = autocrud.create(
        "users", {"name": "Alice", "email": "alice@example.com", "age": 30}
    )

    print(f"建立的使用者 ID: {user_id}")

    # 取得資料
    user = autocrud.get("users", user_id)
    print(f"使用者資料: {user}")

    # 驗證 metadata 欄位
    assert user["id"] == user_id
    assert user["name"] == "Alice"
    assert user["created_time"] is not None
    assert user["created_by"] == "admin"
    assert user["updated_time"] is not None
    assert user["updated_by"] == "admin"

    print("✅ 預設 metadata config 測試通過")


def test_autocrud_override_metadata_config():
    """測試在 register_model 時覆蓋 metadata config"""

    print("\n=== 測試覆蓋 metadata config ===")

    # 建立預設 metadata config
    default_config = MetadataConfig.with_timestamps()

    # 建立 AutoCRUD
    autocrud = AutoCRUD(
        metadata_config=default_config,
        use_plural=False,  # 預設使用單數
    )

    # 建立覆蓋用的 metadata config
    # 覆蓋配置
    override_config = MetadataConfig.with_full_tracking(
        created_time_field="created_at",
        updated_time_field="updated_at",
        created_by_field="author",
        updated_by_field="last_editor",
        get_current_user=lambda: "custom_user",  # 修復為期望的值
    )

    # 註冊模型並覆蓋配置
    autocrud.register_model(
        User,
        metadata_config=override_config,
        use_plural=True,  # 覆蓋預設的單數設定
    )

    # 創建資料
    user_id = autocrud.create("users", {"name": "Bob", "email": "bob@example.com"})

    # 取得資料
    user = autocrud.get("users", user_id)
    print(f"使用者資料: {user}")

    # 驗證覆蓋的 metadata 欄位
    assert user["author"] == "custom_user"  # 使用覆蓋的欄位名稱
    assert user["last_editor"] == "custom_user"  # 修復字段名
    # 驗證覆蓋字段被填充而預設字段為空
    assert user["created_by"] is None  # 預設字段未被使用
    assert user["updated_by"] is None  # 預設字段未被使用
    assert user["created_at"] is not None  # 覆蓋字段被使用
    assert user["updated_at"] is not None  # 覆蓋字段被使用

    print("✅ 覆蓋 metadata config 測試通過")


def test_mixed_configurations():
    """測試混合配置 - 有些模型使用預設，有些覆蓋"""

    print("\n=== 測試混合配置 ===")

    @dataclass
    class Product:
        id: str
        name: str
        price: float
        created_time: Optional[str] = None
        updated_time: Optional[str] = None

    # 建立 AutoCRUD 與預設配置
    autocrud = AutoCRUD(
        metadata_config=MetadataConfig.with_timestamps(),
        id_generator=lambda: f"default_{uuid.uuid4().hex[:6]}",
    )

    # 第一個模型使用預設配置
    autocrud.register_model(User)

    # 第二個模型覆蓋部分配置
    autocrud.register_model(
        Product, id_generator=lambda: f"prod_{uuid.uuid4().hex[:6]}"
    )

    # 測試 User (使用預設 ID 生成器)
    user_id = autocrud.create(
        "users", {"name": "Charlie", "email": "charlie@example.com"}
    )
    assert user_id.startswith("default_")

    # 測試 Product (使用覆蓋的 ID 生成器)
    product_id = autocrud.create("products", {"name": "Laptop", "price": 999.99})
    assert product_id.startswith("prod_")

    print(f"User ID: {user_id}")
    print(f"Product ID: {product_id}")
    print("✅ 混合配置測試通過")


if __name__ == "__main__":
    test_autocrud_with_default_metadata_config()
    test_autocrud_override_metadata_config()
    test_mixed_configurations()
    print("\n🎉 所有測試通過！")
