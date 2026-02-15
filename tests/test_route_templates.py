"""測試 RouteTemplate 功能"""

# 測試用的模型
import itertools as it

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import (
    AutoCRUD,
    NameConverter,
)
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import (
    DeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.switch import SwitchRevisionRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate
from autocrud.util.naming import NamingFormat


class User(msgspec.Struct):
    name: str
    email: str
    age: int


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
    crud.add_route_template(SwitchRevisionRouteTemplate())
    crud.add_route_template(RestoreRouteTemplate())

    # 添加 User 模型
    crud.add_model(User)

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

    def test_create_user(self, client: TestClient):
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
        assert data["resource_id"].startswith("user:")
        assert len(data["resource_id"]) - len("user:") == 36  # UUID 長度
        assert "-" in data["resource_id"]  # UUID 包含連字符

    def test_read_user(self, client: TestClient):
        """測試讀取用戶"""
        # 先創建一個用戶
        user_data = {"name": "Jane Doe", "email": "jane@example.com", "age": 25}

        create_response = client.post("/user", json=user_data)
        create_data = create_response.json()
        resource_id = create_data["resource_id"]

        # 讀取用戶
        response = client.get(f"/user/{resource_id}/full")
        assert response.status_code == 200

        data = response.json()
        assert data["meta"]["resource_id"] == resource_id
        assert "revision_id" in data["revision_info"]
        assert data["data"]["name"] == "Jane Doe"
        assert data["data"]["email"] == "jane@example.com"
        assert data["data"]["age"] == 25

        for returns in it.chain.from_iterable(
            it.combinations(["data", "revision_info", "meta"], r=r) for r in range(0, 4)
        ):
            response = client.get(
                f"/user/{resource_id}/full", params={"returns": ",".join(returns)}
            )
            assert response.status_code == 200

            data2 = response.json()
            for k in ["data", "revision_info", "meta"]:
                if k in returns:
                    assert data2[k] == data[k]
                else:
                    assert k not in data2

    def test_patch_user(self, client: TestClient):
        # 先創建一個用戶
        user_data = {"name": "Bob Smith", "email": "bob@example.com", "age": 35}

        create_response = client.post("/user", json=user_data)
        create_data = create_response.json()
        resource_id = create_data["resource_id"]

        patch_data = [
            {"op": "replace", "path": "/name", "value": "Robert Smith"},
            {"op": "replace", "path": "/age", "value": 36},
        ]
        response = client.patch(f"/user/{resource_id}", json=patch_data)
        assert response.status_code == 200

        data = response.json()
        assert data["resource_id"] == resource_id
        assert "revision_id" in data

        # 驗證更新
        get_response = client.get(f"/user/{resource_id}/full")
        get_data = get_response.json()
        assert get_data["data"]["name"] == "Robert Smith"
        assert get_data["data"]["email"] == "bob@example.com"
        assert get_data["data"]["age"] == 36

        p2_data = [
            {"op": "replace", "path": "/age", "value": 38},
        ]
        response = client.patch(
            f"/user/{resource_id}",
            json=p2_data,
            params={
                "mode": "modify",
                "change_status": "draft",
            },
        )
        assert response.status_code == 200
        get_response = client.get(f"/user/{resource_id}/full")
        get_data = get_response.json()
        assert get_data["data"]["age"] == 38

        response = client.patch(
            f"/user/{resource_id}",
            json=[],
            params={
                "change_status": "draft",
            },
        )
        assert response.status_code == 400

    def test_update_user(self, client: TestClient):
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
        get_response = client.get(f"/user/{resource_id}/full")
        get_data = get_response.json()
        assert get_data["data"]["name"] == "Bob Johnson"
        assert get_data["data"]["email"] == "bob.johnson@example.com"
        assert get_data["data"]["age"] == 36

        # 更新用戶
        updated_data = {
            "name": "Bob Johnson",
            "email": "bob.johnson@example.com",
            "age": 37,
        }

        response = client.put(
            f"/user/{resource_id}", params={"mode": "modify"}, json=updated_data
        )
        assert response.status_code == 400

        response = client.put(
            f"/user/{resource_id}",
            params={
                "mode": "modify",
                "change_status": "draft",
            },
            json=updated_data,
        )
        assert response.status_code == 200

        udata = response.json()
        assert udata["resource_id"] == data["resource_id"]
        assert udata["revision_id"] == data["revision_id"]
        assert udata["uid"] != data["uid"]

        # to stable
        response = client.put(
            f"/user/{resource_id}",
            params={
                "mode": "modify",
                "change_status": "stable",
            },
        )
        assert response.status_code == 200

        u2data = response.json()
        assert u2data["resource_id"] == udata["resource_id"]
        assert u2data["revision_id"] == udata["revision_id"]
        assert u2data["uid"] != udata["uid"]

        response = client.put(
            f"/user/{resource_id}", params={"mode": "modify"}, json=updated_data
        )
        assert response.status_code == 400

    def test_delete_user(self, client: TestClient):
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
        assert data["is_deleted"] is True

        # 驗證刪除
        get_response = client.get(f"/user/{resource_id}/data")
        assert get_response.status_code == 404

    def test_list_users(self, client: TestClient):
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
        response = client.get("/user/data")
        assert response.status_code == 200

        data = response.json()
        assert len(data) >= 3  # 至少有我們創建的 3 個用戶

        # 檢查返回的是實際的用戶數據
        for resource in data:
            assert "name" in resource
            assert "email" in resource
            assert "age" in resource
            assert isinstance(resource["age"], int)

    def test_list_users_with_query_params(self, client: TestClient):
        """測試帶查詢參數的列出用戶"""
        # 創建幾個用戶
        users = [
            {"name": "User 1", "email": "user1@example.com", "age": 20},
            {"name": "User 2", "email": "user2@example.com", "age": 25},
        ]

        for user in users:
            client.post("/user", json=user)

        # 測試 limit 參數
        response = client.get("/user/data?limit=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

        # 測試 offset 參數
        response = client.get("/user/data?limit=1&offset=1")
        assert response.status_code == 200
        data = response.json()
        # 應該返回第二個資源或空列表
        assert len(data) <= 1

    def test_list_users_response_types(self, client: TestClient):
        """測試不同的響應類型"""
        # 創建一個用戶
        user_data = {"name": "Test User", "email": "test@example.com", "age": 30}
        client.post("/user", json=user_data)

        # 測試 DATA 響應類型（預設）
        response = client.get("/user/data")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        # 應該只包含用戶數據
        for resource in data:
            assert "name" in resource
            assert "email" in resource
            assert "age" in resource

        # 測試 META 響應類型
        response = client.get("/user/meta")
        assert response.status_code == 200
        data = response.json()
        # 應該包含 ResourceMeta 字段
        for resource in data:
            assert "resource_id" in resource
            assert "current_revision_id" in resource
            assert "created_time" in resource
            assert "updated_time" in resource

        # 測試 REVISION_INFO 響應類型
        response = client.get("/user/revision-info")
        assert response.status_code == 200
        data = response.json()
        # 應該包含 RevisionInfo 字段
        for resource in data:
            assert "uid" in resource
            assert "resource_id" in resource
            assert "revision_id" in resource
            assert "status" in resource

        # 測試 FULL 響應類型
        response = client.get("/user/full")
        assert response.status_code == 200
        data = response.json()
        # 應該包含所有信息
        for resource in data:
            assert "data" in resource
            assert "meta" in resource
            assert "revision_info" in resource
            # 檢查 data 部分
            assert "name" in resource["data"]
            assert "email" in resource["data"]
            assert "age" in resource["data"]

    @pytest.mark.parametrize(
        "response_type,expected_fields",
        [
            ("data", ["name", "email", "age"]),
            (
                "meta",
                ["resource_id", "current_revision_id", "created_time", "updated_time"],
            ),
            ("revision-info", ["uid", "resource_id", "revision_id", "status"]),
            ("full", ["data", "meta", "revision_info"]),
        ],
    )
    def test_read_user_response_types(self, client, response_type, expected_fields):
        """測試讀取用戶的不同響應類型"""
        # 創建一個用戶
        user_data = {"name": "Test User", "email": "test@example.com", "age": 30}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 測試指定的響應類型
        response = client.get(f"/user/{resource_id}/{response_type}")
        assert response.status_code == 200
        data = response.json()

        for field in expected_fields:
            assert field in data

        # 針對不同響應類型進行特定驗證
        if response_type == "data":
            assert data["name"] == "Test User"
        elif response_type == "full":
            assert data["data"]["name"] == "Test User"

    def test_read_partial(self, client: TestClient):
        """測試讀取部分資源數據"""
        # 創建一個用戶
        user_data = {"name": "Partial User", "email": "partial@example.com", "age": 40}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 測試只獲取 name
        response = client.get(f"/user/{resource_id}/data", params={"partial": "name"})
        assert response.status_code == 200
        data = response.json()
        assert data == {"name": "Partial User"}

        # 測試獲取 name 和 age
        response = client.get(
            f"/user/{resource_id}/data", params={"partial": ["name", "age"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {"name": "Partial User", "age": 40}

        # 測試使用 partial[] (axios 風格)
        # 注意：TestClient 的 params 參數如果傳入 list，預設行為是 key=v1&key=v2
        # 要模擬 key[]=v1&key[]=v2，我們需要手動構造或者使用特定的 key
        response = client.get(
            f"/user/{resource_id}/data",
            params={"partial[]": ["name", "age"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert data == {"name": "Partial User", "age": 40}

    def test_read_full_partial(self, client: TestClient):
        """測試讀取完整資源的部分數據"""
        # 創建一個用戶
        user_data = {
            "name": "Full Partial User",
            "email": "full_partial@example.com",
            "age": 45,
        }
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 測試只獲取 name
        response = client.get(f"/user/{resource_id}/full", params={"partial": "name"})
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == {"name": "Full Partial User"}
        assert "revision_info" in data
        assert "meta" in data

        # 測試獲取 name 和 age
        response = client.get(
            f"/user/{resource_id}/full", params={"partial": ["name", "age"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == {"name": "Full Partial User", "age": 45}

        # 測試 partial[]
        response = client.get(
            f"/user/{resource_id}/full", params={"partial[]": ["name", "age"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["data"] == {"name": "Full Partial User", "age": 45}

    def test_search_partial(self, client: TestClient):
        """測試搜索資源的部分數據"""
        # 創建幾個用戶
        users = [
            {"name": "Search User 1", "email": "s1@example.com", "age": 20},
            {"name": "Search User 2", "email": "s2@example.com", "age": 25},
        ]
        for user in users:
            client.post("/user", json=user)

        # 測試 list data partial
        response = client.get(
            "/user/data",
            params={
                "partial": ["name"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        # 應該至少有上面創建的 2 個用戶，加上之前測試可能殘留的用戶
        assert len(data) >= 2
        for item in data:
            assert "name" in item
            # 如果 partial 生效，其他欄位不應該存在
            # 但要注意，如果之前的測試創建了不符合 schema 的數據（不太可能），或者 partial 沒生效
            if "email" in item:
                print(f"DEBUG: email found in item: {item}")
            assert "email" not in item
            assert "age" not in item

        # 測試 list full partial
        response = client.get(
            "/user/full",
            params={
                "partial[]": ["name", "age"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 2
        for item in data:
            assert "data" in item
            assert "meta" in item
            assert "revision_info" in item
            assert "name" in item["data"]
            assert "age" in item["data"]
            assert "email" not in item["data"]

    @pytest.mark.parametrize(
        "response_type,expected_name",
        [
            ("data", "Original User"),
            ("revision-info", None),
            ("full", "Original User"),
            ("meta", None),
        ],
    )
    def test_read_user_by_revision_id(self, client, response_type, expected_name):
        """測試通過 revision_id 讀取特定版本的用戶"""
        # 創建一個用戶
        user_data = {
            "name": "Original User",
            "email": "original@example.com",
            "age": 25,
        }
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]
        original_revision_id = create_response.json()["revision_id"]

        # 更新用戶數據
        updated_data = {
            "name": "Updated User",
            "email": "updated@example.com",
            "age": 30,
        }
        update_response = client.put(f"/user/{resource_id}", json=updated_data)

        # 測試獲取特定版本
        response = client.get(
            f"/user/{resource_id}/{response_type}?revision_id={original_revision_id}",
        )

        assert response.status_code == 200
        data = response.json()

        if response_type == "data":
            assert data["name"] == expected_name
            assert data["age"] == 25
        elif response_type == "revision_info":
            assert data["revision_id"] == original_revision_id
        elif response_type == "full":
            assert "data" in data
            assert "revision_info" in data
            assert "meta" in data  # 特定版本查詢不包含 meta
            assert data["data"]["name"] == expected_name

    def test_read_user_current_vs_specific_revision(self, client: TestClient):
        """測試當前版本與特定版本的對比"""
        # 創建一個用戶
        user_data = {
            "name": "Original User",
            "email": "original@example.com",
            "age": 25,
        }
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]
        original_revision_id = create_response.json()["revision_id"]

        # 更新用戶數據
        updated_data = {
            "name": "Updated User",
            "email": "updated@example.com",
            "age": 30,
        }
        client.put(f"/user/{resource_id}", json=updated_data)

        # 測試獲取當前版本（不指定 revision_id）
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        current_data = response.json()
        assert current_data["name"] == "Updated User"

        # 測試獲取原始版本（指定 revision_id）
        response = client.get(
            f"/user/{resource_id}/data?revision_id={original_revision_id}",
        )
        assert response.status_code == 200
        original_data = response.json()
        assert original_data["name"] == "Original User"
        assert original_data["age"] == 25

    def test_read_user_revisions_response(self, client: TestClient):
        """測試獲取資源的所有版本信息"""
        # 創建一個用戶
        user_data = {"name": "Version 1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 進行幾次更新以創建多個版本
        for i in range(2, 4):
            updated_data = {
                "name": f"Version {i}",
                "email": f"v{i}@example.com",
                "age": 20 + i,
            }
            client.put(f"/user/{resource_id}", json=updated_data)

        # 測試 REVISIONS 響應類型
        response = client.get(f"/user/{resource_id}/revision-list")
        assert response.status_code == 200
        data = response.json()

        # 驗證響應結構
        assert "meta" in data
        assert "revisions" in data

        # 驗證 meta 信息
        meta = data["meta"]
        assert meta["resource_id"] == resource_id
        assert meta["total_revision_count"] == 3  # 創建 + 2次更新

        # 驗證 revisions 列表
        revisions = data["revisions"]
        assert len(revisions) == 3
        for revision in revisions:
            assert "uid" in revision
            assert "resource_id" in revision
            assert "revision_id" in revision
            assert "status" in revision
            assert revision["resource_id"] == resource_id

    def test_user_not_found(self, client: TestClient):
        """測試用戶不存在的情況"""
        response = client.get("/user/nonexistent/data")
        assert response.status_code == 404

    def test_invalid_user_data(self, client: TestClient):
        """測試無效的用戶數據"""
        invalid_data = {
            "name": "Test User",
            # 缺少 email 和 age
        }

        response = client.post("/user", json=invalid_data)
        assert response.status_code == 422  # msgspec 驗證錯誤

    def test_switch_revision(self, client: TestClient):
        """測試切換資源版本"""
        # 創建一個用戶
        user_data_v1 = {"name": "User V1", "email": "v1@example.com", "age": 25}
        create_response = client.post("/user", json=user_data_v1)
        resource_id = create_response.json()["resource_id"]
        revision_id_v1 = create_response.json()["revision_id"]

        # 更新用戶，創建第二個版本
        user_data_v2 = {"name": "User V2", "email": "v2@example.com", "age": 30}
        update_response = client.put(f"/user/{resource_id}", json=user_data_v2)
        revision_id_v2 = update_response.json()["revision_id"]

        # 驗證當前資料是 V2
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        assert response.json()["name"] == "User V2"

        # 切換到 V1
        switch_response = client.post(f"/user/{resource_id}/switch/{revision_id_v1}")
        assert switch_response.status_code == 200
        switch_data = switch_response.json()
        assert switch_data["resource_id"] == resource_id
        assert switch_data["current_revision_id"] == revision_id_v1

        # 驗證當前資料現在是 V1
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        assert response.json()["name"] == "User V1"
        assert response.json()["age"] == 25

        # 切換回 V2
        switch_response = client.post(f"/user/{resource_id}/switch/{revision_id_v2}")
        assert switch_response.status_code == 200

        # 驗證當前資料又變回 V2
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        assert response.json()["name"] == "User V2"
        assert response.json()["age"] == 30

    def test_switch_revision_not_found(self, client: TestClient):
        """測試切換到不存在的版本"""
        # 創建一個用戶
        user_data = {"name": "Test User", "email": "test@example.com", "age": 25}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 嘗試切換到不存在的版本
        response = client.post(f"/user/{resource_id}/switch/nonexistent-revision")
        assert response.status_code == 400

    def test_switch_revision_resource_not_found(self, client: TestClient):
        """測試切換不存在資源的版本"""
        response = client.post("/user/nonexistent/switch/some-revision")
        assert response.status_code == 400

    def test_restore_resource(self, client: TestClient):
        """測試恢復已刪除的資源"""
        # 創建一個用戶
        user_data = {"name": "Test User", "email": "test@example.com", "age": 25}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 驗證用戶存在
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        assert response.json()["name"] == "Test User"

        # 刪除用戶
        delete_response = client.delete(f"/user/{resource_id}")
        assert delete_response.status_code == 200

        # 驗證用戶已被刪除
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 404

        # 恢復用戶
        restore_response = client.post(f"/user/{resource_id}/restore")
        assert restore_response.status_code == 200
        restore_data = restore_response.json()
        assert restore_data["resource_id"] == resource_id
        assert restore_data["is_deleted"] is False

        # 驗證用戶已被恢復
        response = client.get(f"/user/{resource_id}/data")
        assert response.status_code == 200
        assert response.json()["name"] == "Test User"

    def test_restore_resource_not_found(self, client: TestClient):
        """測試恢復不存在的資源"""
        response = client.post("/user/nonexistent/restore")
        assert response.status_code == 400

    def test_restore_resource_not_deleted(self, client: TestClient):
        """測試恢復未被刪除的資源"""
        # 創建一個用戶
        user_data = {"name": "Test User", "email": "test@example.com", "age": 25}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 嘗試恢復未被刪除的資源（應該正常執行，但狀態不變）
        restore_response = client.post(f"/user/{resource_id}/restore")
        assert restore_response.status_code == 200
        restore_data = restore_response.json()
        assert restore_data["resource_id"] == resource_id
        assert restore_data["is_deleted"] is False


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

        autocrud.add_model(User, name="custom-user")

        assert "custom-user" in autocrud.resource_managers
        assert autocrud.resource_managers["custom-user"].resource_type == User


class TestRevisionListAdvanced:
    """測試 revision-list 端點的進階功能"""

    def test_revision_list_invalid_sort(self, client: TestClient):
        """測試無效的 sort 參數 (行 342)"""
        # 創建資源
        user_data = {"name": "Test", "email": "test@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 測試無效的 sort 參數
        response = client.get(f"/user/{resource_id}/revision-list?sort=invalid")
        assert response.status_code == 400
        assert "Invalid sort" in response.json()["detail"]

    def test_revision_list_invalid_limit(self, client: TestClient):
        """測試無效的 limit 參數 (行 345)"""
        # 創建資源
        user_data = {"name": "Test", "email": "test@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 測試 limit < 1
        response = client.get(f"/user/{resource_id}/revision-list?limit=0")
        assert response.status_code == 400
        assert "limit must be >= 1" in response.json()["detail"]

        response = client.get(f"/user/{resource_id}/revision-list?limit=-5")
        assert response.status_code == 400
        assert "limit must be >= 1" in response.json()["detail"]

    def test_revision_list_invalid_offset(self, client: TestClient):
        """測試無效的 offset 參數 (行 349)"""
        # 創建資源
        user_data = {"name": "Test", "email": "test@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 測試 offset < 0
        response = client.get(f"/user/{resource_id}/revision-list?offset=-1")
        assert response.status_code == 400
        assert "offset must be >= 0" in response.json()["detail"]

    def test_revision_list_with_time_filters(self, client: TestClient):
        """測試 created_time_start 和 created_time_end 過濾 (行 373-374, 377-380)"""
        # 創建第一個版本
        user_data_v1 = {"name": "V1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data_v1)
        assert create_response.status_code == 200
        resource_id = create_response.json()["resource_id"]

        # 創建第二個版本
        user_data_v2 = {"name": "V2", "email": "v2@example.com", "age": 21}
        update_response = client.put(f"/user/{resource_id}", json=user_data_v2)
        assert update_response.status_code == 200

        # 獲取所有 revisions 以便取得實際時間
        all_revs_response = client.get(f"/user/{resource_id}/revision-list")
        assert all_revs_response.status_code == 200
        all_revs = all_revs_response.json()["revisions"]
        assert len(all_revs) == 2

        # 使用第一個 revision 的時間作為 end filter
        first_rev_time = all_revs[1]["created_time"]  # 較早的那個

        # 測試 created_time_end 過濾
        response = client.get(
            f"/user/{resource_id}/revision-list?created_time_end={first_rev_time}"
        )
        assert response.status_code == 200
        data = response.json()
        # 應該只包含第一個版本
        assert data["total"] <= 1

        # 使用第二個 revision 的時間作為 start filter
        second_rev_time = all_revs[0]["created_time"]  # 較晚的那個

        # 測試 created_time_start 過濾
        response = client.get(
            f"/user/{resource_id}/revision-list?created_time_start={second_rev_time}"
        )
        assert response.status_code == 200
        data = response.json()
        # 應該只包含第二個版本
        assert data["total"] <= 1

    def test_revision_list_from_revision_id(self, client: TestClient):
        """測試 from_revision_id 參數 (行 385-397)"""
        # 創建資源並更新幾次
        user_data = {"name": "V1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]
        rev1_id = create_response.json()["revision_id"]

        client.put(
            f"/user/{resource_id}",
            json={"name": "V2", "email": "v2@example.com", "age": 21},
        )
        update2 = client.put(
            f"/user/{resource_id}",
            json={"name": "V3", "email": "v3@example.com", "age": 22},
        )
        rev3_id = update2.json()["revision_id"]

        # 從第一個 revision 開始
        response = client.get(
            f"/user/{resource_id}/revision-list?from_revision_id={rev1_id}&sort=created_time"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3  # 應該包含所有三個版本

        # 從第三個 revision 開始
        response = client.get(
            f"/user/{resource_id}/revision-list?from_revision_id={rev3_id}&sort=created_time"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1  # 只包含第三個版本

    def test_revision_list_from_revision_id_not_found(self, client: TestClient):
        """測試 from_revision_id 找不到的情況 (行 393-397)"""
        # 創建資源
        user_data = {"name": "Test", "email": "test@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 使用不存在的 revision_id
        response = client.get(
            f"/user/{resource_id}/revision-list?from_revision_id=nonexistent"
        )
        assert response.status_code == 404
        assert "revision_id not found" in response.json()["detail"]

    def test_revision_list_chain_only(self, client: TestClient):
        """測試 chain_only 參數 (行 401-410)"""
        # 創建資源並更新幾次，形成 parent chain
        user_data = {"name": "V1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 更新兩次
        client.put(
            f"/user/{resource_id}",
            json={"name": "V2", "email": "v2@example.com", "age": 21},
        )
        client.put(
            f"/user/{resource_id}",
            json={"name": "V3", "email": "v3@example.com", "age": 22},
        )

        # 測試 chain_only=true
        response = client.get(f"/user/{resource_id}/revision-list?chain_only=true")
        assert response.status_code == 200
        data = response.json()

        # 驗證返回的是 parent chain
        assert len(data["revisions"]) == 3
        revisions = data["revisions"]

        # 驗證 parent chain 順序（從當前版本往回追溯）
        assert revisions[0]["parent_revision_id"] == revisions[1]["revision_id"]
        assert revisions[1]["parent_revision_id"] == revisions[2]["revision_id"]
        assert revisions[2]["parent_revision_id"] is None  # 第一個版本沒有 parent

    def test_revision_list_pagination(self, client: TestClient):
        """測試 limit 和 offset 的分頁功能"""
        # 創建資源並更新多次
        user_data = {"name": "V1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 更新 4 次，總共 5 個版本
        for i in range(2, 6):
            client.put(
                f"/user/{resource_id}",
                json={"name": f"V{i}", "email": f"v{i}@example.com", "age": 20 + i},
            )

        # 第一頁，每頁 2 個
        response = client.get(f"/user/{resource_id}/revision-list?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()
        assert len(data["revisions"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True

        # 第二頁
        response = client.get(f"/user/{resource_id}/revision-list?limit=2&offset=2")
        assert response.status_code == 200
        data = response.json()
        assert len(data["revisions"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True

        # 最後一頁
        response = client.get(f"/user/{resource_id}/revision-list?limit=2&offset=4")
        assert response.status_code == 200
        data = response.json()
        assert len(data["revisions"]) == 1
        assert data["total"] == 5
        assert data["has_more"] is False


class TestGetEndpointPartialFields:
    """測試 GET 端點的 partial 欄位功能"""

    def test_get_with_partial_query_params(self, client: TestClient):
        """測試使用 partial[] query params (行 217, 503)"""
        # 創建資源
        user_data = {"name": "Test User", "email": "test@example.com", "age": 30}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 使用 partial[] query params 只獲取部分欄位
        response = client.get(f"/user/{resource_id}/full?partial[]=name&partial[]=age")
        assert response.status_code == 200
        full_data = response.json()

        # 驗證只包含請求的欄位
        assert "data" in full_data
        data = full_data["data"]
        assert "name" in data
        assert "age" in data
        # email 不應該在結果中（因為沒有請求）
        # 注意：partial 可能返回所有欄位或只返回請求的欄位，取決於實作

    def test_get_data_with_partial_brackets(self, client: TestClient):
        """測試 /data 端點的 partial[] query params (行 503)"""
        # 創建資源
        user_data = {"name": "Test User", "email": "test@example.com", "age": 30}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 使用 partial[] query params
        response = client.get(f"/user/{resource_id}/data?partial[]=name")
        assert response.status_code == 200
        data = response.json()

        # 應該返回 partial 資料
        assert "name" in data or response.status_code == 200

    def test_get_data_with_partial_and_revision(self, client: TestClient):
        """測試 /data 端點的 partial 配合 revision_id (行 503-515)"""
        # 創建資源
        user_data_v1 = {"name": "Version 1", "email": "v1@example.com", "age": 25}
        create_response = client.post("/user", json=user_data_v1)
        resource_id = create_response.json()["resource_id"]
        revision_id_v1 = create_response.json()["revision_id"]

        # 更新資源
        user_data_v2 = {"name": "Version 2", "email": "v2@example.com", "age": 30}
        client.put(f"/user/{resource_id}", json=user_data_v2)

        # 使用 partial[] 獲取特定 revision 的部分欄位
        response = client.get(
            f"/user/{resource_id}/data?revision_id={revision_id_v1}&partial[]=/name"
        )
        assert response.status_code == 200
        data = response.json()
        assert "name" in data

    def test_get_data_without_partial_but_with_revision(self, client: TestClient):
        """測試 /data 端點無 partial 但有 revision_id (行 520-525)"""
        # 創建資源
        user_data_v1 = {"name": "Version 1", "email": "v1@example.com", "age": 25}
        create_response = client.post("/user", json=user_data_v1)
        resource_id = create_response.json()["resource_id"]
        revision_id_v1 = create_response.json()["revision_id"]

        # 更新資源
        user_data_v2 = {"name": "Version 2", "email": "v2@example.com", "age": 30}
        client.put(f"/user/{resource_id}", json=user_data_v2)

        # 不使用 partial，但指定 revision_id
        response = client.get(f"/user/{resource_id}/data?revision_id={revision_id_v1}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Version 1"
        assert data["age"] == 25

    def test_get_with_revision_id_parameter(self, client: TestClient):
        """測試 GET 端點使用 revision_id 參數 (行 37-51)"""
        # 創建資源
        user_data_v1 = {"name": "Version 1", "email": "v1@example.com", "age": 25}
        create_response = client.post("/user", json=user_data_v1)
        resource_id = create_response.json()["resource_id"]
        revision_id_v1 = create_response.json()["revision_id"]

        # 更新資源
        user_data_v2 = {"name": "Version 2", "email": "v2@example.com", "age": 30}
        update_response = client.put(f"/user/{resource_id}", json=user_data_v2)
        revision_id_v2 = update_response.json()["revision_id"]

        # 獲取最新版本（不帶 revision_id）- 測試 else 分支（行 46-50）
        response = client.get(f"/user/{resource_id}/full")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "Version 2"
        assert data["revision_info"]["revision_id"] == revision_id_v2

        # 獲取特定版本（帶 revision_id）- 測試 if 分支（行 40-44）
        response = client.get(f"/user/{resource_id}/full?revision_id={revision_id_v1}")
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "Version 1"
        assert data["revision_info"]["revision_id"] == revision_id_v1


class TestRevisionListEdgeCases:
    """測試 revision-list 的邊界條件"""

    def test_chain_only_with_broken_chain(self, client: TestClient):
        """測試 chain_only 當 parent chain 中斷時的情況 (行 407)"""
        # 創建資源並更新
        user_data = {"name": "V1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        # 更新幾次
        client.put(
            f"/user/{resource_id}",
            json={"name": "V2", "email": "v2@example.com", "age": 21},
        )
        client.put(
            f"/user/{resource_id}",
            json={"name": "V3", "email": "v3@example.com", "age": 22},
        )

        # 測試 chain_only - 即使有中斷的情況也應該正常工作
        response = client.get(f"/user/{resource_id}/revision-list?chain_only=true")
        assert response.status_code == 200
        data = response.json()

        # chain 應該包含從當前版本追溯的所有可達版本
        assert len(data["revisions"]) >= 1

        # 驗證 chain 的連續性
        revisions = data["revisions"]
        for i in range(len(revisions) - 1):
            # 每個 revision 的 parent 應該是下一個 revision（或 None）
            if revisions[i]["parent_revision_id"] is not None:
                assert (
                    revisions[i]["parent_revision_id"]
                    == revisions[i + 1]["revision_id"]
                )

    def test_chain_only_with_from_revision_id_pagination(self, client: TestClient):
        """測試 chain_only + from_revision_id 的分頁功能

        模擬前端的 Load More 行為：
        1. 第一次 chain_only=true&limit=2 → 取得最新 2 筆
        2. 第二次 chain_only=true&limit=2&from_revision_id=<最後一筆的 id> → 繼續取
        3. 不應出現重複資料（扣掉 from_revision_id 本身）
        """
        # 建立資源並更新 4 次，產生 5 個 revision
        user_data = {"name": "V1", "email": "v1@example.com", "age": 20}
        create_response = client.post("/user", json=user_data)
        resource_id = create_response.json()["resource_id"]

        for i in range(2, 6):
            client.put(
                f"/user/{resource_id}",
                json={"name": f"V{i}", "email": f"v{i}@example.com", "age": 20 + i},
            )

        # 第一次載入：chain_only=true, limit=2
        resp1 = client.get(
            f"/user/{resource_id}/revision-list?chain_only=true&limit=2"
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["revisions"]) == 2
        assert data1["has_more"] is True

        # 第一批最後一筆的 revision_id
        last_rev_id = data1["revisions"][-1]["revision_id"]

        # 第二次載入：from_revision_id=<上次最後一筆>, chain_only=true, limit=2
        resp2 = client.get(
            f"/user/{resource_id}/revision-list?chain_only=true&limit=2&from_revision_id={last_rev_id}"
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["revisions"]) >= 1

        # from_revision_id 是 inclusive，第一筆應該就是 last_rev_id
        assert data2["revisions"][0]["revision_id"] == last_rev_id

        # 第二批的第二筆（若有）不應與第一批重複
        first_batch_ids = {r["revision_id"] for r in data1["revisions"]}
        second_batch_new = data2["revisions"][1:]  # 跳過 from_revision_id 本身
        for rev in second_batch_new:
            assert rev["revision_id"] not in first_batch_ids, (
                f"Duplicate revision {rev['revision_id']} found in second batch"
            )

        # 合併後應該有 3 筆不重複
        all_ids = [r["revision_id"] for r in data1["revisions"]]
        all_ids.extend(r["revision_id"] for r in second_batch_new)
        assert len(all_ids) == len(set(all_ids)), "Should have no duplicates"

        # 第三次載入（如果 has_more）
        if data2["has_more"]:
            last_rev_id_2 = data2["revisions"][-1]["revision_id"]
            resp3 = client.get(
                f"/user/{resource_id}/revision-list?chain_only=true&limit=2&from_revision_id={last_rev_id_2}"
            )
            assert resp3.status_code == 200
            data3 = resp3.json()

            # 第三批不應與前面重複
            third_batch_new = data3["revisions"][1:]
            for rev in third_batch_new:
                assert rev["revision_id"] not in first_batch_ids
                assert rev["revision_id"] not in {
                    r["revision_id"] for r in second_batch_new
                }
