"""測試 API 端點的 data filtering 功能"""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct, to_builtins
import itertools as it

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.storage_factory import MemoryStorageFactory


# 測試數據模型
class User(Struct, kw_only=True):
    name: str
    email: str
    age: int
    department: str
    salary: float


@pytest.fixture
def test_data():
    """測試數據"""
    return [
        User(
            name="Alice",
            email="alice@engineering.com",
            age=30,
            department="Engineering",
            salary=75000.0,
        ),
        User(
            name="Bob",
            email="bob@marketing.com",
            age=25,
            department="Marketing",
            salary=50000.0,
        ),
        User(
            name="Charlie",
            email="charlie@engineering.com",
            age=35,
            department="Engineering",
            salary=85000.0,
        ),
        User(
            name="Diana",
            email="diana@hr.com",
            age=28,
            department="HR",
            salary=55000.0,
        ),
        User(
            name="Eve",
            email="eve@engineering.com",
            age=32,
            department="Engineering",
            salary=80000.0,
        ),
    ]


@pytest.fixture
def autocrud_with_data(test_data: list[User]):
    """創建包含測試數據的 AutoCRUD 實例"""
    autocrud = AutoCRUD(storage_factory=MemoryStorageFactory())

    # 註冊用戶模型
    autocrud.add_model(
        User,
        name="user",
        indexed_fields=[
            ("department", str),
            ("age", int),
            ("email", str),
            ("salary", float),
        ],
    )

    return autocrud


@pytest.fixture
def test_client(autocrud_with_data: AutoCRUD, test_data: list[User]):
    """創建 FastAPI 測試客戶端"""
    app = FastAPI()
    autocrud_with_data.apply(app)

    client = TestClient(app)

    # 添加測試數據
    for user in test_data:
        user_dict = to_builtins(user)
        response = client.post("/user", json=user_dict)
        assert response.status_code == 200

    return client


def test_data_filtering_equals(test_client: TestClient):
    """測試 equals 操作符"""
    # 測試部門等於 Engineering
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "Engineering"}],
    )

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 3  # Alice, Charlie, Eve
    departments = [user["department"] for user in results]
    assert all(dept == "Engineering" for dept in departments)


def test_data_filtering_greater_than(test_client: TestClient):
    """測試 greater_than 操作符"""
    # 測試年齡大於 30
    data_conditions = json.dumps([{"field_path": "age", "operator": "gt", "value": 30}])

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 2  # Charlie (35), Eve (32)
    ages = [user["age"] for user in results]
    assert all(age > 30 for age in ages)


def test_data_filtering_contains(test_client: TestClient):
    """測試 contains 操作符"""
    # 測試 email 包含 engineering
    data_conditions = json.dumps(
        [{"field_path": "email", "operator": "contains", "value": "engineering"}],
    )

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 3  # Alice, Charlie, Eve
    emails = [user["email"] for user in results]
    assert all("engineering" in email for email in emails)


def test_data_filtering_multiple_conditions(test_client: TestClient):
    """測試多重條件"""
    # 測試部門是 Engineering 且薪水大於等於 80000
    data_conditions = json.dumps(
        [
            {"field_path": "department", "operator": "eq", "value": "Engineering"},
            {
                "field_path": "salary",
                "operator": "gte",
                "value": 80000.0,
            },
        ],
    )

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 2  # Charlie, Eve
    for user in results:
        assert user["department"] == "Engineering"
        assert user["salary"] >= 80000.0


def test_data_filtering_with_metadata_filter(test_client: TestClient):
    """測試 data filtering 與 metadata filtering 結合"""
    # 測試部門是 Engineering 且 is_deleted=false
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "Engineering"}],
    )

    response = test_client.get(
        f"/user/data?data_conditions={data_conditions}&is_deleted=false",
    )
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 3  # Alice, Charlie, Eve


def test_data_filtering_meta_endpoint(test_client: TestClient):
    """測試 meta 端點的 data filtering"""
    # 測試年齡小於 30
    data_conditions = json.dumps([{"field_path": "age", "operator": "lt", "value": 30}])

    response = test_client.get(f"/user/meta?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 2  # Bob (25), Diana (28)

    # 驗證返回的是 metadata
    for meta in results:
        assert "resource_id" in meta
        assert "created_time" in meta
        assert "updated_time" in meta


def test_data_filtering_revision_info_endpoint(test_client: TestClient):
    """測試 revision-info 端點的 data filtering"""
    # 測試部門是 HR
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "HR"}],
    )

    response = test_client.get(f"/user/revision-info?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 1  # Diana

    # 驗證返回的是 revision info
    for revision_info in results:
        assert "uid" in revision_info
        assert "resource_id" in revision_info
        assert "revision_id" in revision_info


def test_data_filtering_full_endpoint(test_client: TestClient):
    """測試 full 端點的 data filtering"""
    # 測試薪水範圍 50000-75000
    data_conditions = json.dumps(
        [
            {
                "field_path": "salary",
                "operator": "gte",
                "value": 50000.0,
            },
            {
                "field_path": "salary",
                "operator": "lte",
                "value": 75000.0,
            },
        ],
    )

    response = test_client.get(f"/user/full?data_conditions={data_conditions}")
    # response = test_client.get(f"/user/full", params={"data_conditions": data_conditions})
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 3  # Alice (75000), Bob (50000), Diana (55000)

    # 驗證返回的是完整信息
    for resource in results:
        assert "data" in resource
        assert "meta" in resource
        assert "revision_info" in resource
        assert 50000.0 <= resource["data"]["salary"] <= 75000.0

    for returns in it.chain.from_iterable(
        it.combinations(["data", "revision_info", "meta"], r=r) for r in range(0, 4)
    ):
        response = test_client.get(
            "/user/full",
            params={"returns": ",".join(returns), "data_conditions": data_conditions},
        )
        assert response.status_code == 200
        rs2 = response.json()
        assert len(rs2) == len(results)
        for r1, r2 in zip(results, rs2):
            for k in ["data", "revision_info", "meta"]:
                if k in returns:
                    assert r1[k] == r2[k]
                else:
                    assert k not in r2


def test_data_filtering_invalid_json(test_client: TestClient):
    """測試無效 JSON 格式"""
    # 提供無效的 JSON
    data_conditions = "invalid json"

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 400
    assert "Invalid data_conditions format" in response.json()["detail"]


def test_data_filtering_invalid_operator(test_client: TestClient):
    """測試無效的操作符"""
    # 提供無效的操作符
    data_conditions = json.dumps(
        [
            {
                "field_path": "department",
                "operator": "invalid_operator",
                "value": "Engineering",
            },
        ],
    )

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 400
    assert "Invalid data_conditions format" in response.json()["detail"]


def test_data_filtering_missing_field(test_client: TestClient):
    """測試缺少必要欄位"""
    # 缺少 field_path
    data_conditions = json.dumps([{"operator": "equals", "value": "Engineering"}])

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 400
    assert "Invalid data_conditions format" in response.json()["detail"]


def test_data_filtering_with_pagination(test_client: TestClient):
    """測試 data filtering 與分頁結合"""
    # 測試部門是 Engineering，限制 2 個結果
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "Engineering"}],
    )

    response = test_client.get(f"/user/data?data_conditions={data_conditions}&limit=2")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 2  # 最多 2 個結果
    departments = [user["department"] for user in results]
    assert all(dept == "Engineering" for dept in departments)


def test_data_filtering_empty_result(test_client: TestClient):
    """測試沒有匹配結果的情況"""
    # 測試不存在的部門
    data_conditions = json.dumps(
        [{"field_path": "department", "operator": "eq", "value": "NonExistentDept"}],
    )

    response = test_client.get(f"/user/data?data_conditions={data_conditions}")
    assert response.status_code == 200

    results = response.json()
    assert len(results) == 0  # 沒有匹配的結果
