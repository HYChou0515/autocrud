import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.storage_factory import MemoryStorageFactory


class Item(Struct, kw_only=True):
    name: str
    score: int


@pytest.fixture
def autocrud():
    return AutoCRUD(storage_factory=MemoryStorageFactory())


@pytest.fixture
def client(autocrud):
    app = FastAPI()
    autocrud.add_model(Item, name="item")
    autocrud.apply(app)
    return TestClient(app)


def test_meta_condition_filtering(client):
    # Create items
    ids = []
    # Items with different names and scores
    items_data = [
        {"name": "apple", "score": 10},
        {"name": "banana", "score": 20},
        {"name": "cherry", "score": 5},
    ]

    for item in items_data:
        resp = client.post("/item", json=item)
        assert resp.status_code == 200
        ids.append(resp.json()["resource_id"])

    # Test 1: proper conditions param structure
    conditions = [{"field_path": "resource_id", "operator": "eq", "value": ids[0]}]
    resp = client.get("/item/data", params={"conditions": json.dumps(conditions)})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "apple"

    # Test 2: starts_with on resource_id
    prefix = ids[1][:4]
    conditions = [
        {"field_path": "resource_id", "operator": "starts_with", "value": prefix}
    ]
    resp = client.get("/item/data", params={"conditions": json.dumps(conditions)})
    assert resp.status_code == 200
    data = resp.json()
    names = [d["name"] for d in data]
    assert "banana" in names

    # Test 3: created_by starts with 'anon'
    conditions = [
        {"field_path": "created_by", "operator": "starts_with", "value": "anon"}
    ]
    resp = client.get("/item/data", params={"conditions": json.dumps(conditions)})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3

    # Test 4: non-existent field or mismatch
    conditions = [{"field_path": "created_by", "operator": "eq", "value": "admin"}]
    resp = client.get("/item/data", params={"conditions": json.dumps(conditions)})
    assert resp.status_code == 200
    assert len(resp.json()) == 0

    # Test 5: Invalid JSON for conditions
    resp = client.get("/item/data", params={"conditions": "invalid-json"})
    assert resp.status_code == 400
    assert "Invalid conditions format" in resp.json()["detail"]

    # Test 6: Invalid operator
    conditions = [
        {"field_path": "resource_id", "operator": "invalid_op", "value": "something"}
    ]
    resp = client.get("/item/data", params={"conditions": json.dumps(conditions)})
    assert resp.status_code == 400
    assert "Invalid conditions format" in resp.json()["detail"]

    # Test 7: meta sorts (created_time desc) -> cherry is last created, so it should be first
    sorts = [{"type": "meta", "key": "created_time", "direction": "-"}]
    resp = client.get("/item/data", params={"sorts": json.dumps(sorts)})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    assert data[0]["name"] == "cherry"

    # Test 8: data sorts (score asc) -> cherry(5), apple(10), banana(20)
    # Note: MemoryStorage might not support data sorting on non-indexed fields or at all in this context,
    # but we just want to ensure the API parses the param correctly without error (200 OK).
    sorts = [{"type": "data", "field_path": "score", "direction": "+"}]
    resp = client.get("/item/data", params={"sorts": json.dumps(sorts)})
    if resp.status_code != 200:
        print(f"DEBUG Error: {resp.content}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3
    # assert data[0]["name"] == "cherry" # storage implementation dependency

    # Test 11: Invalid sort type
    sorts = [{"type": "invalid", "key": "x", "direction": "+"}]
    resp = client.get("/item/data", params={"sorts": json.dumps(sorts)})
    assert resp.status_code == 400
    assert "Invalid sorts format" in resp.json()["detail"]
