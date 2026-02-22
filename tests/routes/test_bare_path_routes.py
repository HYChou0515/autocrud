"""測試 bare path 端點 (GET /{model}/{id} 和 GET /{model})"""

import itertools as it

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.delete import (
    DeleteRouteTemplate,
    RestoreRouteTemplate,
)
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.search import ListRouteTemplate
from autocrud.crud.route_templates.switch import SwitchRevisionRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate


class Hero(msgspec.Struct):
    name: str
    power: str
    level: int


@pytest.fixture
def autocrud():
    """建立 AutoCRUD 實例"""
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(ListRouteTemplate())
    crud.add_route_template(ReadRouteTemplate())
    crud.add_route_template(UpdateRouteTemplate())
    crud.add_route_template(DeleteRouteTemplate())
    crud.add_route_template(SwitchRevisionRouteTemplate())
    crud.add_route_template(RestoreRouteTemplate())
    crud.add_model(Hero)
    return crud


@pytest.fixture
def client(autocrud):
    """建立測試客戶端"""
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


def _create_hero(client: TestClient, name="Superman", power="Flight", level=99):
    resp = client.post("/hero", json={"name": name, "power": power, "level": level})
    assert resp.status_code == 200
    return resp.json()


# ---------------------------------------------------------------------------
# Item-level bare path: GET /{model}/{id}
# ---------------------------------------------------------------------------
class TestBareItemGet:
    """GET /hero/{resource_id} — bare path 端點"""

    def test_default_returns_full(self, client: TestClient):
        """預設回傳 data + revision_info + meta"""
        info = _create_hero(client)
        rid = info["resource_id"]

        resp = client.get(f"/hero/{rid}")
        assert resp.status_code == 200
        body = resp.json()

        assert "data" in body
        assert "revision_info" in body
        assert "meta" in body
        assert body["data"]["name"] == "Superman"
        assert body["meta"]["resource_id"] == rid

    def test_returns_data_only(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]

        resp = client.get(f"/hero/{rid}", params={"returns": "data"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["name"] == "Superman"
        assert "meta" not in body
        assert "revision_info" not in body

    def test_returns_meta_only(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]

        resp = client.get(f"/hero/{rid}", params={"returns": "meta"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["resource_id"] == rid
        assert "data" not in body
        assert "revision_info" not in body

    def test_returns_revision_info_only(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]

        resp = client.get(f"/hero/{rid}", params={"returns": "revision_info"})
        assert resp.status_code == 200
        body = resp.json()
        assert "revision_info" in body
        assert body["revision_info"]["revision_id"] is not None
        assert "data" not in body
        assert "meta" not in body

    def test_returns_data_and_meta(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]

        resp = client.get(f"/hero/{rid}", params={"returns": "data,meta"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["name"] == "Superman"
        assert body["meta"]["resource_id"] == rid
        assert "revision_info" not in body

    def test_all_returns_combinations(self, client: TestClient):
        """所有 returns 組合皆正確"""
        info = _create_hero(client)
        rid = info["resource_id"]

        # 取得 baseline full response
        full = client.get(f"/hero/{rid}").json()

        for r in range(0, 4):
            for combo in it.combinations(["data", "revision_info", "meta"], r=r):
                resp = client.get(f"/hero/{rid}", params={"returns": ",".join(combo)})
                assert resp.status_code == 200
                body = resp.json()
                for k in ["data", "revision_info", "meta"]:
                    if k in combo:
                        assert body[k] == full[k]
                    else:
                        assert k not in body

    def test_with_revision_id(self, client: TestClient):
        """使用 revision_id 查詢特定版本"""
        info = _create_hero(client)
        rid = info["resource_id"]
        rev_id = info["revision_id"]

        resp = client.get(f"/hero/{rid}", params={"revision_id": rev_id})
        assert resp.status_code == 200
        body = resp.json()
        assert body["revision_info"]["revision_id"] == rev_id

    def test_with_partial_fields(self, client: TestClient):
        """使用 partial 取得部分欄位"""
        info = _create_hero(client)
        rid = info["resource_id"]

        resp = client.get(f"/hero/{rid}", params={"partial": ["/name"]})
        assert resp.status_code == 200
        body = resp.json()
        assert "name" in body["data"]
        # partial 只取 name，不該有 level
        assert "level" not in body["data"]

    def test_resource_not_found(self, client: TestClient):
        resp = client.get("/hero/nonexistent-id")
        assert resp.status_code == 404

    def test_matches_full_endpoint(self, client: TestClient):
        """bare path 回傳結果與 /full 一致"""
        info = _create_hero(client)
        rid = info["resource_id"]

        bare = client.get(f"/hero/{rid}").json()
        full = client.get(f"/hero/{rid}/full").json()
        assert bare == full


# ---------------------------------------------------------------------------
# Collection-level bare path: GET /{model}
# ---------------------------------------------------------------------------
class TestBareCollectionGet:
    """GET /hero — bare path 列表端點"""

    def test_default_returns_full_list(self, client: TestClient):
        """預設回傳 full list (data + revision_info + meta)"""
        _create_hero(client, name="A")
        _create_hero(client, name="B")

        resp = client.get("/hero")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 2
        for item in items:
            assert "data" in item
            assert "revision_info" in item
            assert "meta" in item

    def test_returns_data_only_list(self, client: TestClient):
        _create_hero(client, name="C")

        resp = client.get("/hero", params={"returns": "data"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        for item in items:
            assert "data" in item
            assert "meta" not in item
            assert "revision_info" not in item

    def test_returns_meta_only_list(self, client: TestClient):
        _create_hero(client, name="D")

        resp = client.get("/hero", params={"returns": "meta"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        for item in items:
            assert "meta" in item
            assert "data" not in item
            assert "revision_info" not in item

    def test_returns_data_meta_list(self, client: TestClient):
        _create_hero(client, name="E")

        resp = client.get("/hero", params={"returns": "data,meta"})
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        for item in items:
            assert "data" in item
            assert "meta" in item
            assert "revision_info" not in item

    def test_pagination(self, client: TestClient):
        for i in range(5):
            _create_hero(client, name=f"Pager-{i}")

        resp = client.get("/hero", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp2 = client.get("/hero", params={"limit": 2, "offset": 2})
        assert resp2.status_code == 200
        assert len(resp2.json()) == 2

    def test_matches_full_endpoint(self, client: TestClient):
        """bare path 回傳結果與 /full 一致"""
        _create_hero(client, name="Match")

        bare = client.get("/hero", params={"limit": 100}).json()
        full = client.get("/hero/full", params={"limit": 100}).json()
        assert bare == full


# ---------------------------------------------------------------------------
# Deprecated endpoints still work (backward compatibility)
# ---------------------------------------------------------------------------
class TestDeprecatedEndpointsStillWork:
    """舊端點 (deprecated) 仍應正常運作"""

    def test_item_full(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]
        resp = client.get(f"/hero/{rid}/full")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_item_data(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]
        resp = client.get(f"/hero/{rid}/data")
        assert resp.status_code == 200
        assert "name" in resp.json()

    def test_item_meta(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]
        resp = client.get(f"/hero/{rid}/meta")
        assert resp.status_code == 200
        assert "resource_id" in resp.json()

    def test_item_revision_info(self, client: TestClient):
        info = _create_hero(client)
        rid = info["resource_id"]
        resp = client.get(f"/hero/{rid}/revision-info")
        assert resp.status_code == 200
        assert "revision_id" in resp.json()

    def test_collection_full(self, client: TestClient):
        _create_hero(client)
        resp = client.get("/hero/full")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_collection_data(self, client: TestClient):
        _create_hero(client)
        resp = client.get("/hero/data")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_collection_meta(self, client: TestClient):
        _create_hero(client)
        resp = client.get("/hero/meta")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_collection_revision_info(self, client: TestClient):
        _create_hero(client)
        resp = client.get("/hero/revision-info")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ---------------------------------------------------------------------------
# OpenAPI spec verification
# ---------------------------------------------------------------------------
class TestOpenAPISpec:
    """確認 OpenAPI spec 中的 deprecated 標記和新端點"""

    def test_deprecated_marked_in_spec(self, client: TestClient):
        """舊端點在 OpenAPI 中標記為 deprecated"""
        resp = client.get("/openapi.json")
        spec = resp.json()

        deprecated_paths = [
            ("/hero/{resource_id}/full", "get"),
            ("/hero/{resource_id}/data", "get"),
            ("/hero/{resource_id}/meta", "get"),
            ("/hero/{resource_id}/revision-info", "get"),
            ("/hero/full", "get"),
            ("/hero/data", "get"),
            ("/hero/meta", "get"),
            ("/hero/revision-info", "get"),
        ]

        for path, method in deprecated_paths:
            assert path in spec["paths"], f"Path {path} not in spec"
            assert spec["paths"][path][method].get("deprecated") is True, (
                f"{path} should be deprecated"
            )

    def test_new_bare_paths_in_spec(self, client: TestClient):
        """新的 bare path 端點出現在 OpenAPI 中且未被標記為 deprecated"""
        resp = client.get("/openapi.json")
        spec = resp.json()

        # Item-level bare path
        assert "/hero/{resource_id}" in spec["paths"]
        assert spec["paths"]["/hero/{resource_id}"]["get"].get("deprecated") is not True

        # Collection-level bare path
        assert "/hero" in spec["paths"]
        # The /hero path has POST (create) too, check GET specifically
        assert "get" in spec["paths"]["/hero"]
        assert spec["paths"]["/hero"]["get"].get("deprecated") is not True
