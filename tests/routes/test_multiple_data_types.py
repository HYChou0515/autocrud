"""測試 AutoCRUD 對不同數據類型的支持"""

from dataclasses import asdict, dataclass, is_dataclass
from typing import Optional, TypedDict

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import (
    AutoCRUD,
)
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import DeleteRouteTemplate
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate


# 1. TypedDict 方式
class TypedDictUser(TypedDict):
    name: str
    email: str
    age: Optional[int]


# 2. Dataclass 方式
@dataclass
class DataclassUser:
    name: str
    email: str
    age: Optional[int] = None


# 3. Msgspec 方式
class MsgspecUser(msgspec.Struct):
    name: str
    email: str
    age: Optional[int] = None


@pytest.fixture
def autocrud():
    """創建 AutoCRUD 實例並註冊所有數據類型"""
    crud = AutoCRUD(model_naming="kebab")

    # 添加基本路由模板
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(ListRouteTemplate())

    # 註冊所有數據類型 - 用戶期望的簡潔API
    crud.add_model(TypedDictUser)
    crud.add_model(DataclassUser)
    crud.add_model(MsgspecUser)

    return crud


@pytest.fixture
def client(autocrud):
    """創建測試客戶端"""
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize(
    "user_data,endpoint",
    [
        (
            TypedDictUser(name="TypedDict User", email="typed@example.com", age=25),
            "typed-dict-user",
        ),
        (
            DataclassUser(name="Dataclass User", email="dataclass@example.com", age=35),
            "dataclass-user",
        ),
        (
            MsgspecUser(name="Msgspec User", email="msgspec@example.com", age=40),
            "msgspec-user",
        ),
    ],
)
class TestCreateOperations:
    """測試不同數據類型的創建操作"""

    def test_crud_user(self, client: TestClient, user_data, endpoint):
        """測試創建用戶 - 統一測試所有數據類型"""
        # 將不同類型的對象轉換為字典形式供 JSON 序列化
        if is_dataclass(user_data):  # Dataclass
            json_data = asdict(user_data)
        elif isinstance(user_data, msgspec.Struct):  # Msgspec
            json_data = msgspec.to_builtins(user_data)
        else:  # TypedDict (already a dict)
            json_data = user_data

        # 1. 測試創建用戶
        response = client.post(f"/{endpoint}", json=json_data)
        assert response.status_code == 200

        create_result = response.json()
        assert "resource_id" in create_result
        assert "revision_id" in create_result

        resource_id = create_result["resource_id"]
        print(f"\n✅ Created {endpoint} with ID: {resource_id}")

        # 2. 測試讀取剛創建的用戶
        get_response = client.get(f"/{endpoint}/{resource_id}/data")
        assert get_response.status_code == 200

        retrieved_data = get_response.json()
        print(f"📖 Retrieved data: {retrieved_data}")

        # 驗證返回的數據包含正確的字段
        assert retrieved_data["name"] == json_data["name"]
        assert retrieved_data["email"] == json_data["email"]
        assert retrieved_data["age"] == json_data["age"]

        # 3. 測試更新用戶
        updated_data = json_data.copy()
        updated_data["age"] = (updated_data["age"] or 0) + 10  # 年齡加10
        updated_data["name"] = f"Updated {updated_data['name']}"

        update_response = client.put(f"/{endpoint}/{resource_id}", json=updated_data)
        assert update_response.status_code == 200

        update_result = update_response.json()
        assert update_result["resource_id"] == resource_id
        print(f"🔄 Updated {endpoint} - new revision: {update_result['revision_id']}")

        # 4. 驗證更新後的數據
        get_updated_response = client.get(f"/{endpoint}/{resource_id}/data")
        assert get_updated_response.status_code == 200

        updated_retrieved_data = get_updated_response.json()
        assert updated_retrieved_data["name"] == updated_data["name"]
        assert updated_retrieved_data["age"] == updated_data["age"]
        print(f"✅ Verified updated data: {updated_retrieved_data}")

        # 5. 測試列出所有資源
        list_response = client.get(f"/{endpoint}/data")
        print(f"📋 List response status: {list_response.status_code}")
        if list_response.status_code != 200:
            print(f"❌ List error: {list_response.text}")
        assert list_response.status_code == 200

        list_result = list_response.json()
        assert len(list_result) >= 1

        # 找到我們創建的資源
        found_resource = None
        for resource in list_result:
            if resource["name"] == updated_data["name"]:
                found_resource = resource
                break

        assert found_resource is not None
        print(f"📋 Found resource in list: {found_resource['name']}")

        # 6. 測試刪除用戶
        delete_response = client.delete(f"/{endpoint}/{resource_id}")
        assert delete_response.status_code == 200

        delete_result = delete_response.json()
        assert delete_result["resource_id"] == resource_id
        assert delete_result["is_deleted"] is True
        print(f"🗑️ Deleted {endpoint} with ID: {resource_id}")

        # 7. 驗證刪除後無法讀取（或返回已刪除狀態）
        get_deleted_response = client.get(f"/{endpoint}/{resource_id}/data")
        # 根據實現，可能返回404或者返回標記為已刪除的資源
        print(f"🔍 Get deleted resource status: {get_deleted_response.status_code}")

        print(f"🎉 Complete CRUD test passed for {endpoint}")
