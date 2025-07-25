"""測試 TypedDict 與預設值的功能"""

from typing import TypedDict
from autocrud import AutoCRUD


class UserTypedDict(TypedDict):
    id: str
    name: str
    email: str
    age: int
    status: str


def test_typeddict_with_defaults():
    """測試 TypedDict 配合預設值的功能"""
    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()

    # 註冊模型並提供預設值
    autocrud.register_model(
        UserTypedDict, default_values={"status": "active", "age": 18}
    )

    # 創建用戶時不提供 status 和 age，應該使用預設值
    user_id = autocrud.create(
        "user_typed_dicts", {"name": "John Doe", "email": "john@example.com"}
    )

    # 取得創建的用戶
    user = autocrud.get("user_typed_dicts", user_id)
    print("Created user:", user)

    # 驗證預設值是否被應用
    assert user["status"] == "active"
    assert user["age"] == 18
    assert user["name"] == "John Doe"
    assert user["email"] == "john@example.com"

    # 測試覆蓋預設值
    user_id_2 = autocrud.create(
        "user_typed_dicts",
        {
            "name": "Jane Doe",
            "email": "jane@example.com",
            "age": 25,  # 覆蓋預設值
            "status": "inactive",  # 覆蓋預設值
        },
    )

    user_2 = autocrud.get("user_typed_dicts", user_id_2)
    print("Created user 2:", user_2)

    # 驗證覆蓋是否生效
    assert user_2["status"] == "inactive"
    assert user_2["age"] == 25
    assert user_2["name"] == "Jane Doe"
    assert user_2["email"] == "jane@example.com"


if __name__ == "__main__":
    test_typeddict_with_defaults()
    print("✅ TypedDict 預設值測試通過！")
