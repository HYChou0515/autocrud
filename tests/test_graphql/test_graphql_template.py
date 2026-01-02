import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate


class User(msgspec.Struct):
    name: str
    email: str
    age: int


@pytest.fixture
def autocrud():
    """Create AutoCRUD instance with GraphQL support"""
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_model(User, indexed_fields=["name", "age"])
    return crud


@pytest.fixture
def client(autocrud):
    """Create test client"""
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


def test_graphql_flow(client: TestClient):
    # 1. Create a user
    user_data = {"name": "Alice", "email": "alice@example.com", "age": 25}
    response = client.post("/user", json=user_data)
    assert response.status_code == 200
    created_user = response.json()
    resource_id = created_user["resource_id"]

    # 2. Query via GraphQL
    query = """
    query GetUser($resourceId: String!) {
        user(resourceId: $resourceId) {
            data {
                name
                email
                age
            }
            meta {
                resourceId
                createdTime
            }
        }
    }
    """

    response = client.post(
        "/graphql", json={"query": query, "variables": {"resourceId": resource_id}}
    )

    assert response.status_code == 200
    data = response.json()
    assert "errors" not in data
    assert data["data"]["user"]["data"]["name"] == "Alice"
    assert data["data"]["user"]["data"]["age"] == 25
    assert data["data"]["user"]["meta"]["resourceId"] == resource_id


def test_graphql_list(client: TestClient):
    # 1. Create users
    client.post("/user", json={"name": "Bob", "email": "bob@example.com", "age": 30})
    client.post(
        "/user", json={"name": "Charlie", "email": "charlie@example.com", "age": 35}
    )

    # 2. List via GraphQL
    query = """
    query ListUsers {
        user_list(query: {limit: 10}) {
            data {
                name
            }
        }
    }
    """

    response = client.post("/graphql", json={"query": query})

    assert response.status_code == 200
    data = response.json()
    assert "errors" not in data
    users = data["data"]["user_list"]
    assert len(users) >= 2
    names = [u["data"]["name"] for u in users]
    assert "Bob" in names
    assert "Charlie" in names


def test_graphql_search(client: TestClient):
    # 1. Create users
    client.post("/user", json={"name": "Dave", "email": "dave@example.com", "age": 40})

    # 2. Search via GraphQL
    query = """
    query SearchUsers {
        user_list(query: {
            dataConditions: [
                {condition: {fieldPath: "name", operator: equals, value: "Dave"}}
            ]
        }) {
            data {
                name
            }
        }
    }
    """

    response = client.post("/graphql", json={"query": query})

    assert response.status_code == 200
    data = response.json()
    assert "errors" not in data
    users = data["data"]["user_list"]
    assert len(users) == 1
    assert users[0]["data"]["name"] == "Dave"


def test_graphql_nested_filter(client: TestClient):
    # Create users
    client.post(
        "/user", json={"name": "Alice", "email": "alice@example.com", "age": 20}
    )
    client.post("/user", json={"name": "Bob", "email": "bob@example.com", "age": 30})
    client.post(
        "/user", json={"name": "Charlie", "email": "charlie@example.com", "age": 40}
    )

    # Query: (age < 25) OR (age > 35) -> Alice and Charlie
    query = """
    query ListUsers {
        user_list(query: {
            dataConditions: [
                {
                    group: {
                        operator: or_op,
                        conditions: [
                            {
                                condition: {
                                    fieldPath: "age",
                                    operator: less_than,
                                    value: 25
                                }
                            },
                            {
                                condition: {
                                    fieldPath: "age",
                                    operator: greater_than,
                                    value: 35
                                }
                            }
                        ]
                    }
                }
            ]
        }) {
            data {
                name
            }
        }
    }
    """

    response = client.post("/graphql", json={"query": query})

    assert response.status_code == 200
    data = response.json()
    if "errors" in data:
        print(data["errors"])
    assert "errors" not in data
    users = data["data"]["user_list"]
    assert len(users) == 2
    names = {u["data"]["name"] for u in users}
    assert "Alice" in names
    assert "Charlie" in names
    assert "Bob" not in names
