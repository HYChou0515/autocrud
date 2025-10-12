"""測試 RouteTemplate 功能"""

# 測試用的模型
import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
import itertools as it

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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
