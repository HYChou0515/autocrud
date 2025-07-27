"""測試 TypedDict 預設值在 FastAPI 路由中的效果"""

from typing import TypedDict
from autocrud import AutoCRUD


class UserTypedDict(TypedDict):
    id: str
    name: str
    email: str
    age: int
    status: str


def test_fastapi_routes_with_defaults():
    """測試 FastAPI 路由生成時預設值的效果"""

    # 創建 AutoCRUD 實例
    autocrud = AutoCRUD()

    # 註冊模型並提供預設值
    autocrud.register_model(
        UserTypedDict, default_values={"status": "active", "age": 18}
    )

    # 取得 create request model
    crud = autocrud.get_crud("user_typed_dicts")
    create_model = crud.schema_analyzer.get_create_model()

    print("Create Request Model 欄位：")

    # 檢查 model 欄位
    if hasattr(create_model, "model_fields"):
        # Pydantic v2
        for field_name, field_info in create_model.model_fields.items():
            required = field_info.is_required()
            print(f"  {field_name}: required = {required}")

            # 有預設值的欄位應該不是必填的
            if field_name in ["status", "age"]:
                assert not required, f"{field_name} 應該是選填的因為有預設值"
            elif field_name in ["name", "email"]:
                assert required, f"{field_name} 應該是必填的"

    # 測試實際創建一個實例
    print("\n測試創建實例：")
    # 創建實例時不提供有預設值的欄位
    instance = create_model(name="Test User", email="test@example.com")
    print(f"成功創建實例: {instance}")

    # 測試包含部分欄位
    instance_2 = create_model(
        name="Test User 2",
        email="test2@example.com",
        age=25,  # 覆蓋預設值
    )
    print(f"成功創建實例 2: {instance_2}")


if __name__ == "__main__":
    test_fastapi_routes_with_defaults()
    print("\n✅ FastAPI 路由預設值測試通過！")
