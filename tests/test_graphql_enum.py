import enum
import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate


class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"


class User(msgspec.Struct):
    name: str
    role: UserRole


@pytest.fixture
def autocrud():
    """Create AutoCRUD instance with GraphQL support"""
    crud = AutoCRUD(model_naming="kebab")
    crud.add_route_template(CreateRouteTemplate())
    crud.add_route_template(GraphQLRouteTemplate())
    crud.add_model(User)
    return crud


@pytest.fixture
def client(autocrud):
    """Create test client"""
    app = FastAPI()
    router = APIRouter()
    autocrud.apply(router)
    app.include_router(router)
    return TestClient(app)


def test_graphql_enum(client: TestClient):
    # 1. Create a user with Enum
    user_data = {"name": "Alice", "role": "admin"}
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
                role
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
    assert (
        data["data"]["user"]["data"]["role"] == "ADMIN"
    )  # Strawberry converts Enum to name by default? Or value?
    # Strawberry Enums are serialized as strings (names) usually in response.
    # But wait, if we use dynamic enum creation, strawberry uses the Enum member name as the GraphQL enum value.
    # Let's check what we get.
