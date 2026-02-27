"""
測試 /count endpoint 應回傳所有匹配資源的真實總數，不受 default limit 限制。
Issue #156: Dashboard count 最多只顯示 10 個。
"""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud import AutoCRUD


class Item(Struct):
    name: str
    category: str = "default"


@pytest.fixture
def client() -> TestClient:
    """建立測試客戶端"""
    app: FastAPI = FastAPI()
    router: APIRouter = APIRouter()
    crud: AutoCRUD = AutoCRUD()
    crud.add_model(
        Item,
        indexed_fields=[("category", str)],
    )
    crud.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def many_items(client: TestClient) -> list[str]:
    """建立超過 default limit (10) 的測試資料"""
    created_ids = []
    for i in range(25):
        response = client.post(
            "/item", json={"name": f"item-{i}", "category": "A" if i < 15 else "B"}
        )
        assert response.status_code == 200
        created_ids.append(response.json()["resource_id"])
    return created_ids


class TestCountEndpointIgnoresDefaultLimit:
    """count endpoint 不應受到 default limit=10 的限制"""

    def test_count_returns_total_without_limit(
        self, client: TestClient, many_items: list[str]
    ) -> None:
        """count 應回傳全部 25 筆，即使沒有傳 limit 參數"""
        response = client.get("/item/count")
        assert response.status_code == 200
        assert response.json() == 25

    def test_count_with_explicit_limit_still_counts_all(
        self, client: TestClient, many_items: list[str]
    ) -> None:
        """即使有傳 limit 參數，count 也不應受 limit 限制"""
        response = client.get("/item/count", params={"limit": 5})
        assert response.status_code == 200
        # count endpoint 應該忽略 limit，回傳真實總數
        assert response.json() == 25

    def test_count_with_filter(self, client: TestClient, many_items: list[str]) -> None:
        """count 搭配 filter 條件應回傳正確的篩選總數"""
        response = client.get(
            "/item/count",
            params={
                "data_conditions": '[{"field_path": "category", "operator": "eq", "value": "A"}]'
            },
        )
        assert response.status_code == 200
        assert response.json() == 15

    def test_count_with_qb_filter(
        self, client: TestClient, many_items: list[str]
    ) -> None:
        """count 搭配 QB 表達式應回傳正確的篩選總數"""
        response = client.get(
            "/item/count",
            params={"qb": "QB['category'] == 'B'"},
        )
        assert response.status_code == 200
        assert response.json() == 10

    def test_list_still_respects_default_limit(
        self, client: TestClient, many_items: list[str]
    ) -> None:
        """確保 list endpoint 仍遵循 default limit=10"""
        response = client.get("/item")
        assert response.status_code == 200
        assert len(response.json()) == 10
