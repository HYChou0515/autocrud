"""測試泛型類型支援"""

from dataclasses import dataclass
from typing import Optional
from autocrud import SingleModelCRUD, AutoCRUD
from autocrud.storage import MemoryStorage


@dataclass
class User:
    id: str
    name: str
    email: str
    age: Optional[int] = None


@dataclass
class Product:
    id: str
    name: str
    price: float
    description: Optional[str] = None


class TestGenericTyping:
    """測試泛型類型功能"""

    def test_single_model_crud_generic_typing(self):
        """測試 SingleModelCRUD 的泛型類型支援"""
        storage = MemoryStorage()
        # 創建類型安全的 SingleModelCRUD
        user_crud: SingleModelCRUD[User] = SingleModelCRUD(
            model=User, storage=storage, resource_name="users"
        )

        # 驗證基本屬性
        assert user_crud.model == User
        assert user_crud.resource_name == "users"

        # 測試創建操作
        user_id = user_crud.create(
            {"name": "John", "email": "john@example.com", "age": 30}
        )
        assert isinstance(user_id, str)

        # 測試獲取操作
        user = user_crud.get(user_id)
        assert user is not None
        assert user["name"] == "John"
        assert user["id"] == user_id

    def test_autocrud_generic_typing(self):
        """測試 AutoCRUD 的泛型類型支援"""
        # 創建多模型 CRUD 系統
        multi_crud = AutoCRUD()

        # 註冊模型
        multi_crud.register_model(User)
        multi_crud.register_model(Product)

        # 驗證註冊
        assert multi_crud.get_model("users") == User
        assert multi_crud.get_model("products") == Product

        # 測試操作
        user_id = multi_crud.create(
            "users", {"name": "Alice", "email": "alice@example.com"}
        )
        assert isinstance(user_id, str)

        user = multi_crud.get("users", user_id)
        assert user is not None
        assert user["name"] == "Alice"
