"""測試 RouteTemplate 功能"""

import pytest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient

from autocrud.v03.crud.core import (
    AutoCRUD,
    CreateRouteTemplate,
    ReadRouteTemplate,
    UpdateRouteTemplate,
    DeleteRouteTemplate,
    ListRouteTemplate,
    NameConverter,
    NamingFormat,
)
from autocrud.v03.resource_manager.basic import (
    IStorage,
)
from autocrud.v03.resource_manager.core import SimpleStorage
from autocrud.v03.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.v03.resource_manager.resource_store.simple import MemoryResourceStore


# 測試用的模型
import msgspec


class User(msgspec.Struct):
    name: str
    email: str
    age: int


def create_user_storage() -> IStorage[User]:
    """創建用戶存儲"""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore[User](resource_type=User)
    return SimpleStorage(meta_store, resource_store)


@pytest.fixture
def autocrud():
    """創建 AutoCRUD 實例"""
    crud = AutoCRUD(model_naming="kebab")

    # 添加所有路由模板
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(ListRouteTemplate())

    # 添加 User 模型
    crud.add_model(User, storage_factory=create_user_storage)

    return crud


@pytest.fixture
def client(autocrud):
    """創建測試客戶端"""
    app = FastAPI()
    router = APIRouter()

    # 應用路由
    autocrud.apply(router)
    app.include_router(router)

    return TestClient(app)


class TestNameConverter:
    """測試 NameConverter 功能"""

    def test_pascal_to_kebab(self):
        converter = NameConverter("UserProfile")
        assert converter.to(NamingFormat.KEBAB) == "user-profile"

    def test_camel_to_kebab(self):
        converter = NameConverter("userProfile")
        assert converter.to(NamingFormat.KEBAB) == "user-profile"

    def test_snake_to_kebab(self):
        converter = NameConverter("user_profile")
        assert converter.to(NamingFormat.KEBAB) == "user-profile"

    def test_kebab_to_pascal(self):
        converter = NameConverter("user-profile")
        assert converter.to(NamingFormat.PASCAL) == "UserProfile"

    def test_same_format(self):
        converter = NameConverter("UserProfile")
        assert converter.to(NamingFormat.SAME) == "UserProfile"


class TestRouteTemplates:
    """測試 RouteTemplate 功能"""

    def test_create_user(self, client):
        """測試創建用戶"""
        user_data = {"name": "John Doe", "email": "john@example.com", "age": 30}

        response = client.post("/user", json=user_data)
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
        assert response.status_code == 200

        data = response.json()
        assert "resource_id" in data
        assert "revision_id" in data
        # resource_id 是 UUID 格式
        assert len(data["resource_id"]) == 36  # UUID 長度
        assert "-" in data["resource_id"]  # UUID 包含連字符

    def test_read_user(self, client):
        """測試讀取用戶"""
        # 先創建一個用戶
        user_data = {"name": "Jane Doe", "email": "jane@example.com", "age": 25}

        create_response = client.post("/user", json=user_data)
        create_data = create_response.json()
        resource_id = create_data["resource_id"]

        # 讀取用戶
        response = client.get(f"/user/{resource_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["resource_id"] == resource_id
        assert "revision_id" in data
        assert data["data"]["name"] == "Jane Doe"
        assert data["data"]["email"] == "jane@example.com"
        assert data["data"]["age"] == 25

    def test_update_user(self, client):
        """測試更新用戶"""
        # 先創建一個用戶
        user_data = {"name": "Bob Smith", "email": "bob@example.com", "age": 35}

        create_response = client.post("/user", json=user_data)
        create_data = create_response.json()
        resource_id = create_data["resource_id"]

        # 更新用戶
        updated_data = {
            "name": "Bob Johnson",
            "email": "bob.johnson@example.com",
            "age": 36,
        }

        response = client.put(f"/user/{resource_id}", json=updated_data)
        assert response.status_code == 200

        data = response.json()
        assert data["resource_id"] == resource_id
        assert "revision_id" in data

        # 驗證更新
        get_response = client.get(f"/user/{resource_id}")
        get_data = get_response.json()
        assert get_data["data"]["name"] == "Bob Johnson"
        assert get_data["data"]["email"] == "bob.johnson@example.com"
        assert get_data["data"]["age"] == 36

    def test_delete_user(self, client):
        """測試刪除用戶"""
        # 先創建一個用戶
        user_data = {"name": "Alice Cooper", "email": "alice@example.com", "age": 28}

        create_response = client.post("/user", json=user_data)
        create_data = create_response.json()
        resource_id = create_data["resource_id"]

        # 刪除用戶
        response = client.delete(f"/user/{resource_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["resource_id"] == resource_id
        assert data["deleted"] is True

        # 驗證刪除
        get_response = client.get(f"/user/{resource_id}")
        assert get_response.status_code == 404

    def test_list_users(self, client):
        """測試列出用戶"""
        # 創建幾個用戶
        users = [
            {"name": "User 1", "email": "user1@example.com", "age": 20},
            {"name": "User 2", "email": "user2@example.com", "age": 25},
            {"name": "User 3", "email": "user3@example.com", "age": 30},
        ]

        for user in users:
            client.post("/user", json=user)

        # 列出用戶
        response = client.get("/user")
        assert response.status_code == 200

        data = response.json()
        assert "resources" in data
        assert len(data["resources"]) >= 3  # 至少有我們創建的 3 個用戶

        # 檢查返回的是實際的用戶數據
        for resource in data["resources"]:
            assert "name" in resource
            assert "email" in resource
            assert "age" in resource
            assert isinstance(resource["age"], int)

    def test_list_users_with_query_params(self, client):
        """測試帶查詢參數的列出用戶"""
        # 創建幾個用戶
        users = [
            {"name": "User 1", "email": "user1@example.com", "age": 20},
            {"name": "User 2", "email": "user2@example.com", "age": 25},
        ]

        for user in users:
            client.post("/user", json=user)

        # 測試 limit 參數
        response = client.get("/user?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data["resources"]) <= 1

        # 測試 offset 參數
        response = client.get("/user?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        # 應該返回第二個資源或空列表
        assert len(data["resources"]) <= 1

    def test_user_not_found(self, client):
        """測試用戶不存在的情況"""
        response = client.get("/user/nonexistent")
        assert response.status_code == 404

    def test_invalid_user_data(self, client):
        """測試無效的用戶數據"""
        invalid_data = {
            "name": "Test User",
            # 缺少 email 和 age
        }

        response = client.post("/user", json=invalid_data)
        assert response.status_code == 422  # msgspec 驗證錯誤


class TestAutoCRUD:
    """測試 AutoCRUD 類別"""

    def test_resource_name_conversion(self):
        """測試資源名稱轉換"""
        autocrud = AutoCRUD(model_naming="kebab")

        class UserProfile:
            pass

        name = autocrud._resource_name(UserProfile)
        assert name == "user-profile"

    def test_custom_naming_function(self):
        """測試自定義命名函數"""

        def custom_naming(model_type):
            return f"api_{model_type.__name__.lower()}"

        autocrud = AutoCRUD(model_naming=custom_naming)

        class TestModel:
            pass

        name = autocrud._resource_name(TestModel)
        assert name == "api_testmodel"

    def test_add_model_with_custom_name(self):
        """測試添加模型時使用自定義名稱"""
        autocrud = AutoCRUD()

        autocrud.add_model(
            User, name="custom-user", storage_factory=create_user_storage
        )

        assert "custom-user" in autocrud.resource_managers
        assert autocrud.resource_managers["custom-user"].resource_type == User


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
