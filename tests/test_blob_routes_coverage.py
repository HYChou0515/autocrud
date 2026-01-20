from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import UNSET

from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.resource_manager.core import ResourceManager
from autocrud.types import Binary


class MockBlobStore:
    def get_url(self, file_id):
        return None

    def put(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        pass

    def exists(self, *args, **kwargs):
        return True


class MockManager(ResourceManager):
    def __init__(self, blob_data=UNSET, content_type=UNSET):
        self.blob_store = MockBlobStore()
        self._blob_data = blob_data
        self._content_type = content_type

    def get_blob(self, file_id):
        return Binary(
            file_id=file_id, data=self._blob_data, content_type=self._content_type
        )

    def get_blob_url(self, file_id):
        return None


def test_blob_data_missing_500():
    manager = MockManager(blob_data=UNSET)

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test", manager, router)

    # TestClient needs a proper FastAPI app with exception handlers
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/blobs/file1")
    assert response.status_code == 500
    assert response.json()["detail"] == "Blob data missing"


def test_blob_content_type_handling():
    manager = MockManager(blob_data=b"xyz", content_type="image/png")

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test", manager, router)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/blobs/file1")
    assert response.status_code == 200
    assert response.content == b"xyz"
    assert response.headers["content-type"] == "image/png"


def test_blob_default_content_type():
    manager = MockManager(blob_data=b"xyz", content_type=UNSET)

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test", manager, router)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    response = client.get("/blobs/file1")
    assert response.status_code == 200
    assert response.content == b"xyz"
    assert response.headers["content-type"] == "application/octet-stream"


def test_blob_not_found_404():
    class MockManagerNotFound(MockManager):
        def get_blob(self, file_id):
            raise FileNotFoundError("not found")

    manager = MockManagerNotFound(blob_data=UNSET)

    template = BlobRouteTemplate()
    router = APIRouter()
    template.apply("test", manager, router)

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/blobs/missing_id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Blob not found"
