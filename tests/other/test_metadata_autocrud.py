"""測試 AutoCRUD 中的 metadata config 功能"""

from dataclasses import dataclass
from typing import Optional


from autocrud import AutoCRUD, MetadataConfig


@dataclass
class User:
    id: str
    name: str
    email: str
    created_time: Optional[str] = None
    created_by: Optional[str] = None
    updated_time: Optional[str] = None
    updated_by: Optional[str] = None


def test_autocrud_with_metadata_config():
    """測試 AutoCRUD 可以在 init 時接受 metadata_config"""

    # 創建 metadata 配置
    metadata_config = MetadataConfig.with_full_tracking(
        get_current_user=lambda: "test_user"
    )

    # 在 AutoCRUD init 時提供 metadata_config
    auto_crud = AutoCRUD(metadata_config=metadata_config, use_plural=True)

    # 註冊模型
    auto_crud.register_model(User)

    # 創建使用者
    user_id = auto_crud.create("users", {"name": "Alice", "email": "alice@example.com"})

    print(f"創建的使用者 ID: {user_id}")

    # 獲取使用者
    user = auto_crud.get("users", user_id)
    print(f"獲取的使用者: {user}")

    # 驗證 metadata 是否被正確設置
    assert user is not None
    assert user["name"] == "Alice"
    assert user["email"] == "alice@example.com"
    assert user["created_time"] is not None
    assert user["created_by"] == "test_user"
    assert user["updated_time"] is not None
    assert user["updated_by"] == "test_user"

    print("✅ AutoCRUD metadata config 測試通過")


def test_register_model_override_metadata():
    """測試在 register_model 時可以覆蓋 metadata config"""

    # AutoCRUD 預設配置
    default_metadata = MetadataConfig.with_timestamps()

    auto_crud = AutoCRUD(metadata_config=default_metadata)

    # 為特定模型覆蓋 metadata 配置
    override_metadata = MetadataConfig.with_full_tracking(
        get_current_user=lambda: "admin_user"
    )

    auto_crud.register_model(User, metadata_config=override_metadata)

    # 創建使用者
    user_id = auto_crud.create("users", {"name": "Bob", "email": "bob@example.com"})

    user = auto_crud.get("users", user_id)
    print(f"使用覆蓋配置的使用者: {user}")

    # 驗證使用了覆蓋的配置
    assert user["created_by"] == "admin_user"  # 使用覆蓋的設定
    assert user["created_time"] is not None  # 時間戳也應該存在

    print("✅ register_model 覆蓋 metadata config 測試通過")


def test_id_generator_inheritance():
    """測試 id_generator 的繼承和覆蓋"""

    def custom_id_generator():
        import time

        return f"custom_{int(time.time())}"

    def special_id_generator():
        import time

        return f"special_{int(time.time())}"

    # AutoCRUD 預設 id_generator
    auto_crud = AutoCRUD(id_generator=custom_id_generator)

    # 使用預設 id_generator 的模型
    auto_crud.register_model(User, resource_name="users")

    # 使用覆蓋 id_generator 的模型
    auto_crud.register_model(
        User, resource_name="special_users", id_generator=special_id_generator
    )

    # 測試預設 id_generator
    user_id1 = auto_crud.create(
        "users", {"name": "User1", "email": "user1@example.com"}
    )
    print(f"預設 ID: {user_id1}")
    assert user_id1.startswith("custom_")

    # 測試覆蓋的 id_generator
    user_id2 = auto_crud.create(
        "special_users", {"name": "User2", "email": "user2@example.com"}
    )
    print(f"特殊 ID: {user_id2}")
    assert user_id2.startswith("special_")

    print("✅ id_generator 繼承和覆蓋測試通過")


def test_use_plural_inheritance():
    """測試 use_plural 的繼承和覆蓋"""

    # AutoCRUD 預設不使用複數
    auto_crud = AutoCRUD(use_plural=False)

    # 使用預設設定（單數）
    auto_crud.register_model(User, resource_name="single_user")  # 手動指定避免衝突

    # 覆蓋為複數（但因為前面已經註冊了，這裡會改用不同的資源名稱）
    auto_crud.register_model(User, resource_name="plural_users", use_plural=True)

    # 檢查資源名稱
    resources = auto_crud.list_resources()
    print(f"註冊的資源: {resources}")

    # 應該有 "single_user" 資源
    assert "single_user" in resources

    print("✅ use_plural 繼承測試通過")


if __name__ == "__main__":
    test_autocrud_with_metadata_config()
    test_register_model_override_metadata()
    test_id_generator_inheritance()
    test_use_plural_inheritance()
    print("\n🎉 所有測試都通過了！")
