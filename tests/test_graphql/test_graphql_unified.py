import datetime as dt

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from specstar.crud.core import SpecStar
from specstar.crud.route_templates.graphql import GraphQLRouteTemplate


class User(msgspec.Struct):
    name: str
    age: int


class Post(msgspec.Struct):
    title: str
    content: str


@pytest.fixture
def specstar():
    """Create SpecStar instance with GraphQL support"""
    spec = SpecStar(model_naming="kebab")
    spec.add_route_template(GraphQLRouteTemplate())
    spec.add_model(User, indexed_fields=["name"])
    spec.add_model(Post, indexed_fields=["title"])
    return spec


@pytest.fixture
def client(specstar):
    """Create test client"""
    app = FastAPI()
    router = APIRouter()
    specstar.apply(router)
    app.include_router(router)
    return TestClient(app)


def test_unified_graphql_endpoint(client: TestClient):
    # 1. Create data via REST (simulated or just assume empty for now, but we need data to query)
    # Since we didn't add CreateRouteTemplate, we can't create via REST easily unless we add it.
    # Or we can manually inject data into resource managers.

    # Let's add CreateRouteTemplate to make it easier
    pass


def test_unified_schema_structure(client: TestClient):
    # Introspection query to verify both types exist
    query = """
    {
        __schema {
            queryType {
                fields {
                    name
                }
            }
        }
    }
    """
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()

    field_names = [f["name"] for f in data["data"]["__schema"]["queryType"]["fields"]]
    print(f"Field names: {field_names}")
    assert "user" in field_names
    assert "user_list" in field_names
    assert "post" in field_names
    assert "post_list" in field_names


def test_query_multiple_resources(specstar, client):
    # Inject data manually
    user_rm = specstar.get_resource_manager(User)
    post_rm = specstar.get_resource_manager(Post)

    with user_rm.meta_provide("admin", dt.datetime.now()):
        user_rm.create(User(name="Alice", age=30))

    with post_rm.meta_provide("admin", dt.datetime.now()):
        post_rm.create(Post(title="Hello", content="World"))

    # Query both
    query = """
    query {
        user_list {
            data {
                name
                age
            }
        }
        post_list {
            data {
                title
                content
            }
        }
    }
    """
    response = client.post("/graphql", json={"query": query})
    assert response.status_code == 200
    data = response.json()

    assert len(data["data"]["user_list"]) == 1
    assert data["data"]["user_list"][0]["data"]["name"] == "Alice"

    assert len(data["data"]["post_list"]) == 1
    assert data["data"]["post_list"][0]["data"]["title"] == "Hello"
