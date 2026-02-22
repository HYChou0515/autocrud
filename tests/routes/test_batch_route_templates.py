"""測試 BatchDeleteRouteTemplate 和 BatchRestoreRouteTemplate 功能"""

import json

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import (
    BatchDeleteRouteTemplate,
    BatchRestoreRouteTemplate,
    DeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.crud.route_templates.search import ListRouteTemplate


class User(msgspec.Struct):
    name: str
    email: str
    age: int


@pytest.fixture
def autocrud():
    """創建 AutoCRUD 實例"""
    crud = AutoCRUD(model_naming="kebab")

    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ListRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(RestoreRouteTemplate())
    crud.add_route_template(BatchDeleteRouteTemplate())
    crud.add_route_template(BatchRestoreRouteTemplate())

    crud.add_model(User, indexed_fields=["name", "email", "age"])

    return crud


@pytest.fixture
def client(autocrud):
    """創建測試客戶端"""
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


def _create_users(client: TestClient, users: list[dict]) -> list[str]:
    """建立多個用戶並回傳 resource_id 列表"""
    resource_ids = []
    for user_data in users:
        resp = client.post("/user", json=user_data)
        assert resp.status_code == 200
        resource_ids.append(resp.json()["resource_id"])
    return resource_ids


class TestBatchDelete:
    """測試 BatchDeleteRouteTemplate"""

    def test_batch_delete_all(self, client: TestClient):
        """建立多筆資源 → DELETE /{model}?limit=100 → 驗證回傳 list[ResourceMeta] 且 is_deleted=True"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
        _create_users(client, users)

        resp = client.delete("/user", params={"limit": 100})
        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data, list)
        assert len(data) == 3
        for meta in data:
            assert meta["is_deleted"] is True

    def test_batch_delete_forces_is_deleted_false(self, client: TestClient):
        """即使 query 傳 is_deleted=True 也只會刪除非刪除資源（is_deleted 被強制為 False）"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
        ]
        resource_ids = _create_users(client, users)

        # 先刪除 Alice
        client.delete(f"/user/{resource_ids[0]}")

        # 用 is_deleted=True 做 batch delete，但應被強制為 False，
        # 所以只會刪到還沒被刪除的 Bob
        resp = client.delete("/user", params={"limit": 100, "is_deleted": True})
        assert resp.status_code == 200
        data = resp.json()

        assert len(data) == 1
        assert data[0]["resource_id"] == resource_ids[1]
        assert data[0]["is_deleted"] is True

    def test_batch_delete_with_data_conditions(self, client: TestClient):
        """帶 data_conditions 篩選（例如 age > 25）只刪除符合條件的資源"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 20},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
        _create_users(client, users)

        conditions = json.dumps([{"field_path": "age", "operator": "gt", "value": 25}])
        resp = client.delete(
            "/user", params={"limit": 100, "data_conditions": conditions}
        )
        assert resp.status_code == 200
        data = resp.json()

        # 只有 Alice(30) 和 Charlie(35) 符合 age > 25
        assert len(data) == 2
        deleted_names = set()
        for meta in data:
            assert meta["is_deleted"] is True
            # 確認被刪除的資源
            deleted_names.add(meta["resource_id"])

        # Bob 不應被刪除，驗證他仍存在
        list_resp = client.get("/user/meta", params={"limit": 100})
        remaining = list_resp.json()
        assert len(remaining) == 1  # 只剩 Bob

    def test_batch_delete_empty_result(self, client: TestClient):
        """無符合條件的資源 → 回傳空 list"""
        # 不建立任何資源
        resp = client.delete("/user", params={"limit": 100})
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_batch_delete_with_limit(self, client: TestClient):
        """測試 limit 參數限制刪除數量"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
        _create_users(client, users)

        # 只刪除前 2 筆
        resp = client.delete("/user", params={"limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # 還有 1 筆存活
        list_resp = client.get("/user/meta", params={"limit": 100})
        remaining = list_resp.json()
        assert len(remaining) == 1


class TestBatchRestore:
    """測試 BatchRestoreRouteTemplate"""

    def test_batch_restore_all(self, client: TestClient):
        """建立多筆 → 逐一刪除 → POST /{model}/restore?limit=100 → 驗證回傳 is_deleted=False"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
        resource_ids = _create_users(client, users)

        # 逐一刪除
        for rid in resource_ids:
            client.delete(f"/user/{rid}")

        # Batch restore
        resp = client.post("/user/restore", params={"limit": 100})
        assert resp.status_code == 200
        data = resp.json()

        assert isinstance(data, list)
        assert len(data) == 3
        for meta in data:
            assert meta["is_deleted"] is False

    def test_batch_restore_forces_is_deleted_true(self, client: TestClient):
        """驗證 is_deleted 強制為 True（只恢復已刪除的資源）"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
        ]
        resource_ids = _create_users(client, users)

        # 只刪除 Alice
        client.delete(f"/user/{resource_ids[0]}")

        # 即使傳 is_deleted=False，也應被強制為 True，只恢復 Alice
        resp = client.post("/user/restore", params={"limit": 100, "is_deleted": False})
        assert resp.status_code == 200
        data = resp.json()

        assert len(data) == 1
        assert data[0]["resource_id"] == resource_ids[0]
        assert data[0]["is_deleted"] is False

    def test_batch_restore_with_data_conditions(self, client: TestClient):
        """帶條件篩選的 batch restore"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 20},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
        resource_ids = _create_users(client, users)

        # 全部刪除
        for rid in resource_ids:
            client.delete(f"/user/{rid}")

        # 只恢復 age > 25 的
        conditions = json.dumps([{"field_path": "age", "operator": "gt", "value": 25}])
        resp = client.post(
            "/user/restore", params={"limit": 100, "data_conditions": conditions}
        )
        assert resp.status_code == 200
        data = resp.json()

        # 只有 Alice(30) 和 Charlie(35) 符合 age > 25
        assert len(data) == 2
        for meta in data:
            assert meta["is_deleted"] is False

    def test_batch_restore_empty_result(self, client: TestClient):
        """空結果 → 回傳空 list"""
        # 沒有已刪除的資源
        resp = client.post("/user/restore", params={"limit": 100})
        assert resp.status_code == 200
        data = resp.json()
        assert data == []

    def test_batch_restore_with_limit(self, client: TestClient):
        """測試 limit 參數限制恢復數量"""
        users = [
            {"name": "Alice", "email": "alice@example.com", "age": 30},
            {"name": "Bob", "email": "bob@example.com", "age": 25},
            {"name": "Charlie", "email": "charlie@example.com", "age": 35},
        ]
        resource_ids = _create_users(client, users)

        # 全部刪除
        for rid in resource_ids:
            client.delete(f"/user/{rid}")

        # 只恢復 2 筆
        resp = client.post("/user/restore", params={"limit": 2})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # 還有 1 筆仍為已刪除
        list_resp = client.get("/user/meta", params={"limit": 100, "is_deleted": True})
        still_deleted = list_resp.json()
        assert len(still_deleted) == 1
