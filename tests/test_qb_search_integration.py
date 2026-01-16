"""
測試 QB 表達式與 Search API 的整合
"""

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI, APIRouter
from msgspec import Struct

from autocrud import AutoCRUD


class User(Struct):
    name: str
    age: int
    department: str
    active: bool = True


@pytest.fixture
def client():
    """創建測試客戶端"""
    app = FastAPI()
    router = APIRouter()
    crud = AutoCRUD()
    crud.add_model(
        User,
        indexed_fields=[
            ("age", int),
            ("department", str),
            ("active", bool),
            ("name", str),  # 添加 name 來支持 complex expression 測試
        ],
    )
    crud.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def sample_users(client):
    """創建測試數據"""
    users = [
        {"name": "Alice", "age": 25, "department": "Engineering", "active": True},
        {"name": "Bob", "age": 30, "department": "Marketing", "active": True},
        {"name": "Charlie", "age": 35, "department": "Engineering", "active": False},
        {"name": "David", "age": 28, "department": "Sales", "active": True},
        {"name": "Eve", "age": 32, "department": "Engineering", "active": True},
    ]

    created_ids = []
    for user_data in users:
        response = client.post("/user", json=user_data)
        assert response.status_code == 200
        created_ids.append(response.json()["resource_id"])

    return created_ids


def test_qb_simple_equality(client, sample_users):
    """測試簡單的相等條件"""
    response = client.get(
        "/user/data", params={"qb": "QB['department'] == 'Engineering'"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    assert all(u["department"] == "Engineering" for u in data)


def test_qb_greater_than(client, sample_users):
    """測試大於條件"""
    response = client.get("/user/data", params={"qb": "QB['age'].gt(30)"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["age"] > 30 for u in data)


def test_qb_and_condition(client, sample_users):
    """測試 AND 條件"""
    response = client.get(
        "/user/data",
        params={"qb": "QB['age'].gt(25) & QB['department'].eq('Engineering')"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["age"] > 25 and u["department"] == "Engineering" for u in data)


def test_qb_or_condition(client, sample_users):
    """測試 OR 條件"""
    response = client.get(
        "/user/data", params={"qb": "QB['age'].lt(26) | QB['age'].gt(33)"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert all(u["age"] < 26 or u["age"] > 33 for u in data)


def test_qb_not_condition(client, sample_users):
    """測試 NOT 條件"""
    response = client.get("/user/data", params={"qb": "~QB['active'].eq(True)"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert all(not u["active"] for u in data)


def test_qb_with_limit_and_offset(client, sample_users):
    """測試分頁參數與 QB 表達式結合"""
    # 首先確認總共有3筆 Engineering
    response = client.get(
        "/user/data", params={"qb": "QB['department'].eq('Engineering')"}
    )
    assert response.status_code == 200
    assert len(response.json()) == 3

    # 測試 limit=2, offset=1，應該返回2筆
    response = client.get(
        "/user/data",
        params={"qb": "QB['department'].eq('Engineering')", "limit": 2, "offset": 1},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_qb_with_sorting(client, sample_users):
    """測試排序與 QB 表達式結合"""
    response = client.get(
        "/user/data", params={"qb": "QB['department'].eq('Engineering').sort('-age')"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    # 驗證按年齡降序排列
    ages = [u["age"] for u in data]
    assert ages == sorted(ages, reverse=True)


def test_qb_bracket_syntax(client, sample_users):
    """測試方括號語法"""
    # 使用 indexed field 來搜尋
    response = client.get("/user/data", params={"qb": "QB['age'] == 25"})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["age"] == 25
    assert data[0]["name"] == "Alice"


def test_qb_conflict_with_data_conditions(client, sample_users):
    """測試 qb 與 data_conditions 衝突時應返回錯誤"""
    response = client.get(
        "/user/data",
        params={
            "qb": "QB['age'].gt(25)",
            "data_conditions": '[{"field_path": "department", "operator": "eq", "value": "Engineering"}]',
        },
    )
    # FastAPI 會將 422 包裝成 400，但 detail 中會包含原始訊息
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "data_conditions" in detail


def test_qb_conflict_with_conditions(client, sample_users):
    """測試 qb 與 conditions 衝突時應返回錯誤"""
    response = client.get(
        "/user/data",
        params={
            "qb": "QB['age'].gt(25)",
            "conditions": '[{"field_path": "resource_id", "operator": "starts_with", "value": "user"}]',
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "conditions" in detail


def test_qb_conflict_with_sorts(client, sample_users):
    """測試 qb 與 sorts 衝突時應返回錯誤"""
    response = client.get(
        "/user/data",
        params={
            "qb": "QB['age'].gt(25)",
            "sorts": '[{"type": "data", "field_path": "age", "direction": "+"}]',
        },
    )
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "sorts" in detail


def test_qb_invalid_expression(client, sample_users):
    """測試無效的 QB 表達式應返回 400"""
    response = client.get("/user/data", params={"qb": "QB['age'].invalid_method(25)"})
    assert response.status_code == 400
    assert "Invalid QB expression" in response.json()["detail"]


def test_qb_with_meta_endpoint(client, sample_users):
    """測試 QB 表達式在 /meta endpoint 的使用"""
    response = client.get(
        "/user/meta", params={"qb": "QB['department'].eq('Engineering')"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3


def test_qb_with_full_endpoint(client, sample_users):
    """測試 QB 表達式在 /full endpoint 的使用"""
    response = client.get("/user/full", params={"qb": "QB['age'].between(25, 30)"})
    assert response.status_code == 200
    data = response.json()
    # between 是包含邊界的，25-30 包含 Alice(25), Bob(30), David(28)
    assert len(data) == 3
    assert all(25 <= item["data"]["age"] <= 30 for item in data)


def test_qb_with_count_endpoint(client, sample_users):
    """測試 QB 表達式在 /count endpoint 的使用"""
    response = client.get(
        "/user/count", params={"qb": "QB['department'].eq('Engineering')"}
    )
    assert response.status_code == 200
    assert response.json() == 3


def test_qb_complex_expression(client, sample_users):
    """測試複雜的 QB 表達式"""
    response = client.get(
        "/user/data",
        params={
            "qb": "(QB['age'].gt(25) & QB['department'].eq('Engineering')) | QB['name'].eq('Bob')"
        },
    )
    assert response.status_code == 200
    data = response.json()
    # (age > 25 AND department == Engineering): Charlie (35), Eve (32)
    # OR name == Bob: Bob (30, Marketing)
    # 總共: Charlie + Eve + Bob = 3
    assert len(data) == 3
