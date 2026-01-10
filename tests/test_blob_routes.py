import base64
from contextlib import contextmanager
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct
from autocrud.crud.core import AutoCRUD
from autocrud.types import Binary


class UserWithAvatar(Struct):
    name: str
    avatar: Binary


@pytest.fixture
def autocrud():
    app = AutoCRUD()
    app.add_model(UserWithAvatar)
    return app


@pytest.fixture
def client(autocrud):
    app = FastAPI()
    autocrud.apply(app)
    return TestClient(app)


def test_blob_lifecycle(client):
    """Test full cycle of blob: create, get metadata, get content"""
    # 1. Create a user with avatar
    raw_content = b"fake_image_content_12345"
    b64_content = base64.b64encode(raw_content).decode("utf-8")

    response = client.post(
        "/user-with-avatar", json={"name": "User1", "avatar": {"data": b64_content}}
    )
    assert response.status_code == 200
    res_info = response.json()
    resource_id = res_info["resource_id"]

    # 2. Get the resource data to find file_id
    response = client.get(f"/user-with-avatar/{resource_id}/data")
    assert response.status_code == 200
    user_data = response.json()

    # Verify binary processing happened
    assert "data" not in user_data["avatar"]
    file_id = user_data["avatar"]["file_id"]
    assert file_id is not None
    assert user_data["avatar"]["size"] == len(raw_content)

    # 3. Get the blob content
    response = client.get(f"/user-with-avatar/{resource_id}/blobs/{file_id}")
    assert response.status_code == 200
    assert response.content == raw_content
    # Depending on implementation, media type might be specific or generic
    assert response.headers["content-type"] == "text/plain; charset=utf-8"


def test_blob_resource_not_found(client):
    """Test getting blob for non-existent resource"""
    response = client.get("/user-with-avatar/nonexistent/blobs/somefileid")
    # route template catches Exception during get(resource_id) and returns 403
    # Wait, checking implementation:
    # except Exception: raise HTTPException(status_code=403, detail="Permission denied or Resource not found")
    assert response.status_code == 403


def test_blob_file_not_found(client):
    """Test getting non-existent blob for existing resource"""
    # Create resource first
    raw_content = b"content"
    b64_content = base64.b64encode(raw_content).decode("utf-8")
    response = client.post(
        "/user-with-avatar", json={"name": "User1", "avatar": {"data": b64_content}}
    )
    resource_id = response.json()["resource_id"]

    # Requests valid resource but invalid blob id
    response = client.get(f"/user-with-avatar/{resource_id}/blobs/nonexistent_file_id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Blob not found"


def test_blob_store_not_configured():
    """Test behavior when blob store is not configured"""
    # We need to manually construct AutoCRUD/ResourceManager to simulate no blob_store
    # or Mock AutoCRUD to return a manager without blob_store

    from autocrud.resource_manager.core import ResourceManager, SimpleStorage
    from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
    from autocrud.resource_manager.meta_store.simple import MemoryMetaStore

    from autocrud.crud.route_templates.blob import BlobRouteTemplate
    from fastapi import APIRouter

    # Create manager without blob_store
    store = SimpleStorage(MemoryMetaStore(), MemoryResourceStore())
    manager = ResourceManager(UserWithAvatar, storage=store, blob_store=None)

    # Setup Router manually to test the template logic which might skip route or fail
    # Logic in BlobRouteTemplate.apply:
    # if resource_manager.blob_store is None: return

    template = BlobRouteTemplate()
    router = APIRouter()

    # This should NOT add the route
    template.apply("user-with-avatar", manager, router)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Route shouldn't exist
    response = client.get("/blobs/456")
    assert response.status_code == 404  # Not Found because route not registered


def test_blob_route_not_implemented_error():
    """Test 501 when get_blob raises NotImplementedError"""
    # Create a mock that passes isinstance(ResourceManager)
    # easiest way is to create a subclass or minimal implementation

    from autocrud.resource_manager.core import ResourceManager

    class MockBlobStore:
        def get_url(self, file_id):
            return None

    class MockManager(ResourceManager):
        def __init__(self):
            self.blob_store = MockBlobStore()  # Not None to pass check in apply

        def get(self, resource_id):
            return "ok"

        def get_blob(self, file_id):
            raise NotImplementedError("Mocked")

        @contextmanager
        def meta_provide(self, **kwargs):
            yield

    manager = MockManager()

    # Setup Route
    from autocrud.crud.route_templates.blob import BlobRouteTemplate
    from fastapi import APIRouter

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test-model", manager, router)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/blobs/456")
    assert response.status_code == 501
    assert response.json()["detail"] == "Blob store not configured"


def test_blob_route_skip_non_resource_manager():
    """Test that apply returns early if manager is not ResourceManager instance"""

    class NotAManager:
        pass

    manager = NotAManager()

    from autocrud.crud.route_templates.blob import BlobRouteTemplate
    from fastapi import APIRouter

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test-model", manager, router)

    assert len(router.routes) == 0


def test_blob_redirect():
    """Test that blob route redirects if blob store provides a URL"""
    from autocrud.resource_manager.core import ResourceManager

    class MockRedirectBlobStore:
        def get_url(self, file_id):
            return f"https://example.com/blobs/{file_id}"

        def put(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            pass

        def exists(self, *args, **kwargs):
            return True

    class MockManager(ResourceManager):
        def __init__(self):
            self.blob_store = MockRedirectBlobStore()

        def get(self, resource_id):
            return "ok"  # dummy

        @contextmanager
        def meta_provide(self, **kwargs):
            yield

    manager = MockManager()

    from autocrud.crud.route_templates.blob import BlobRouteTemplate
    from fastapi import APIRouter

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test-model", manager, router)

    app = FastAPI()
    app.include_router(router)
    # Don't follow redirects to assert 307
    client = TestClient(app)

    response = client.get("/blobs/my-file-id", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "https://example.com/blobs/my-file-id"
