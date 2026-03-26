"""Tests for blob upload-session endpoints.

Covers the full two-step session lifecycle using a ``MemoryBlobStore``
which natively supports upload sessions.

Routes under test:
- ``POST   /blobs/upload-sessions``
- ``GET    /blobs/upload-sessions/{upload_id}``
- ``PUT    /blobs/upload-sessions/{upload_id}/content``
- ``POST   /blobs/upload-sessions/{upload_id}/finalize``
- ``POST   /blobs/upload-sessions/{upload_id}/abort``
"""

import io
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import Binary, BlobUploadSession

# ---------------------------------------------------------------------------
# Test model — needs at least one Binary field so blob routes get mounted
# ---------------------------------------------------------------------------


class FileHolder(Struct):
    name: str
    attachment: Binary


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def autocrud():
    app = AutoCRUD()
    app.add_model(FileHolder)
    return app


@pytest.fixture
def client(autocrud):
    app = FastAPI()
    autocrud.apply(app)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_BYTES = b"hello blob session"
SAMPLE_CONTENT_TYPE = "text/plain"


def _create_session(client, content_type=SAMPLE_CONTENT_TYPE, size=None):
    body = {}
    if content_type is not None:
        body["content_type"] = content_type
    if size is not None:
        body["size"] = size
    resp = client.post("/blobs/upload-sessions", json=body)
    return resp


def _put_content(
    client, upload_id, data=SAMPLE_BYTES, content_type=SAMPLE_CONTENT_TYPE
):
    return client.put(
        f"/blobs/upload-sessions/{upload_id}/content",
        files={"file": ("test.bin", io.BytesIO(data), content_type)},
    )


def _finalize(client, upload_id):
    return client.post(f"/blobs/upload-sessions/{upload_id}/finalize")


def _abort(client, upload_id):
    return client.post(f"/blobs/upload-sessions/{upload_id}/abort")


def _get_session(client, upload_id):
    return client.get(f"/blobs/upload-sessions/{upload_id}")


# ---------------------------------------------------------------------------
# Tests — create
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_returns_upload_id(self, client):
        resp = _create_session(client)
        assert resp.status_code == 200
        data = resp.json()
        assert "upload_id" in data
        assert len(data["upload_id"]) > 0

    def test_upload_method_is_proxy(self, client):
        resp = _create_session(client)
        data = resp.json()
        assert data["upload_method"] == "proxy"

    def test_upload_url_contains_upload_id(self, client):
        resp = _create_session(client)
        data = resp.json()
        assert data["upload_id"] in data["upload_url"]

    def test_initial_status_is_pending(self, client):
        resp = _create_session(client)
        data = resp.json()
        assert data["status"] == "pending"

    def test_content_type_preserved(self, client):
        resp = _create_session(client, content_type="image/png")
        data = resp.json()
        assert data["content_type"] == "image/png"

    def test_size_preserved(self, client):
        resp = _create_session(client, size=42)
        data = resp.json()
        assert data["size"] == 42


# ---------------------------------------------------------------------------
# Tests — get session
# ---------------------------------------------------------------------------


class TestGetSession:
    def test_pending_session(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        resp = _get_session(client, upload_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_unknown_upload_id_404(self, client):
        resp = _get_session(client, uuid.uuid4().hex)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — put content
# ---------------------------------------------------------------------------


class TestPutContent:
    def test_stores_bytes_and_updates_status(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        resp = _put_content(client, upload_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "uploaded"

        # Also verify via GET
        sess = _get_session(client, upload_id).json()
        assert sess["status"] == "uploaded"
        assert sess["size"] == len(SAMPLE_BYTES)

    def test_unknown_upload_id_404(self, client):
        resp = _put_content(client, uuid.uuid4().hex)
        assert resp.status_code == 404

    def test_cannot_put_content_twice(self, client):
        """Once content has been uploaded (status=uploaded), a second PUT is rejected."""
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        resp = _put_content(client, upload_id)
        assert resp.status_code == 409

    def test_cannot_put_content_after_finalize(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        _finalize(client, upload_id)
        resp = _put_content(client, upload_id)
        assert resp.status_code == 409

    def test_cannot_put_content_after_abort(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _abort(client, upload_id)
        resp = _put_content(client, upload_id)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tests — finalize
# ---------------------------------------------------------------------------


class TestFinalize:
    def test_returns_binary_metadata(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        resp = _finalize(client, upload_id)
        assert resp.status_code == 200
        data = resp.json()
        assert "file_id" in data
        assert data["size"] == len(SAMPLE_BYTES)
        assert data["content_type"] == SAMPLE_CONTENT_TYPE
        # raw data must NOT be in the response
        assert "data" not in data or data.get("data") is None

    def test_finalize_without_content_409(self, client):
        """Cannot finalize a session that has no content (status=pending)."""
        upload_id = _create_session(client).json()["upload_id"]
        resp = _finalize(client, upload_id)
        assert resp.status_code == 409

    def test_finalize_twice_409(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        resp1 = _finalize(client, upload_id)
        assert resp1.status_code == 200
        resp2 = _finalize(client, upload_id)
        assert resp2.status_code == 409

    def test_unknown_upload_id_404(self, client):
        resp = _finalize(client, uuid.uuid4().hex)
        assert resp.status_code == 404

    def test_session_status_after_finalize(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        _finalize(client, upload_id)
        sess = _get_session(client, upload_id).json()
        assert sess["status"] == "finalized"


# ---------------------------------------------------------------------------
# Tests — abort
# ---------------------------------------------------------------------------


class TestAbort:
    def test_abort_pending_session(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        resp = _abort(client, upload_id)
        assert resp.status_code == 204
        sess = _get_session(client, upload_id).json()
        assert sess["status"] == "aborted"

    def test_abort_uploaded_session(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        resp = _abort(client, upload_id)
        assert resp.status_code == 204
        sess = _get_session(client, upload_id).json()
        assert sess["status"] == "aborted"

    def test_abort_finalized_session_409(self, client):
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        _finalize(client, upload_id)
        resp = _abort(client, upload_id)
        assert resp.status_code == 409

    def test_unknown_upload_id_404(self, client):
        resp = _abort(client, uuid.uuid4().hex)
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Tests — full happy path (end-to-end)
# ---------------------------------------------------------------------------


class TestFullHappyPath:
    def test_create_upload_finalize_then_download(self, client):
        """Create session → PUT content → finalize → download via /blobs/{file_id}."""
        # 1. Create session
        sess_resp = _create_session(client, content_type="application/octet-stream")
        assert sess_resp.status_code == 200
        upload_id = sess_resp.json()["upload_id"]

        # 2. Upload content
        content = b"binary-content-for-e2e-test"
        put_resp = _put_content(
            client, upload_id, data=content, content_type="application/octet-stream"
        )
        assert put_resp.status_code == 200

        # 3. Finalize
        fin_resp = _finalize(client, upload_id)
        assert fin_resp.status_code == 200
        file_id = fin_resp.json()["file_id"]
        assert file_id  # non-empty

        # 4. Download via existing blob route
        dl_resp = client.get(f"/blobs/{file_id}")
        assert dl_resp.status_code == 200
        assert dl_resp.content == content

    def test_create_abort_then_finalize_fails(self, client):
        """After abort, finalize must fail."""
        upload_id = _create_session(client).json()["upload_id"]
        _put_content(client, upload_id)
        _abort(client, upload_id)
        resp = _finalize(client, upload_id)
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Tests — native blob store session path (covers "try native first" branches)
# ---------------------------------------------------------------------------


class _NativeBlobStore:
    """Fake blob store that natively supports upload sessions.

    Not a real ``IBlobStore`` subclass — duck-typed for route template patching.
    """

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._blobs: dict[str, bytes] = {}

    # Required by IBlobStore contract (not abstract but needed for route mount)
    def put(self, data, *, key=None, content_type="application/octet-stream"):
        fid = key or uuid.uuid4().hex
        self._blobs[fid] = data
        return Binary(file_id=fid, size=len(data), content_type=content_type)

    def get(self, file_id):
        if file_id not in self._blobs:
            raise FileNotFoundError(file_id)
        return Binary(file_id=file_id, data=self._blobs[file_id])

    def exists(self, file_id):
        return file_id in self._blobs

    def get_url(self, file_id):
        return None

    # Native session support
    def create_upload_session(self, *, key=None, content_type=None, size=None):
        uid = uuid.uuid4().hex
        fid = key or uuid.uuid4().hex
        sess = BlobUploadSession(
            upload_id=uid,
            file_id=fid,
            status="pending",
            upload_method="proxy",
            content_type=content_type or "application/octet-stream",
            size=size,
        )
        self._sessions[uid] = {
            "session": sess,
            "data": None,
        }
        return sess

    def get_upload_session(self, upload_id):
        if upload_id not in self._sessions:
            raise FileNotFoundError(upload_id)
        return self._sessions[upload_id]["session"]

    def upload_to_session(self, upload_id, data):
        if upload_id not in self._sessions:
            raise FileNotFoundError(upload_id)
        self._sessions[upload_id]["data"] = data
        sess = self._sessions[upload_id]["session"]
        # Return a new struct with updated status
        self._sessions[upload_id]["session"] = BlobUploadSession(
            upload_id=sess.upload_id,
            file_id=sess.file_id,
            status="uploaded",
            upload_method=sess.upload_method,
            content_type=sess.content_type,
            size=len(data),
        )

    def finalize_upload_session(self, upload_id):
        if upload_id not in self._sessions:
            raise FileNotFoundError(upload_id)
        entry = self._sessions[upload_id]
        stored = self.put(entry["data"], content_type=entry["session"].content_type)
        self._sessions[upload_id]["session"] = BlobUploadSession(
            upload_id=upload_id,
            file_id=stored.file_id,
            status="finalized",
            upload_method="proxy",
            content_type=stored.content_type,
            size=stored.size,
        )
        return stored

    def abort_upload_session(self, upload_id):
        if upload_id not in self._sessions:
            raise FileNotFoundError(upload_id)
        sess = self._sessions[upload_id]["session"]
        self._sessions[upload_id]["session"] = BlobUploadSession(
            upload_id=upload_id,
            file_id=sess.file_id,
            status="aborted",
            upload_method="proxy",
        )


@pytest.fixture
def native_client():
    """Client backed by a blob store with native session support."""

    crud = AutoCRUD()
    crud.add_model(FileHolder)
    app = FastAPI()
    crud.apply(app)

    # Patch the blob store on the route template after apply
    native_store = _NativeBlobStore()
    for tmpl in crud.route_templates:
        if hasattr(tmpl, "_blob_store") and tmpl._blob_store is not None:
            tmpl._blob_store = native_store
            break

    return TestClient(app)


class TestNativeSessionPath:
    """Exercise the 'try native first' code paths."""

    def test_create_session_native(self, native_client):
        resp = _create_session(native_client)
        assert resp.status_code == 200
        data = resp.json()
        assert "upload_id" in data
        assert data["status"] == "pending"

    def test_get_session_native(self, native_client):
        upload_id = _create_session(native_client).json()["upload_id"]
        resp = _get_session(native_client, upload_id)
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    def test_put_content_native(self, native_client):
        upload_id = _create_session(native_client).json()["upload_id"]
        resp = _put_content(native_client, upload_id)
        assert resp.status_code == 200

    def test_finalize_native(self, native_client):
        upload_id = _create_session(native_client).json()["upload_id"]
        _put_content(native_client, upload_id)
        resp = _finalize(native_client, upload_id)
        assert resp.status_code == 200
        data = resp.json()
        assert "file_id" in data
        assert data["size"] == len(SAMPLE_BYTES)

    def test_abort_native(self, native_client):
        upload_id = _create_session(native_client).json()["upload_id"]
        resp = _abort(native_client, upload_id)
        assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Tests — blob store not configured (501) for session routes
# ---------------------------------------------------------------------------


@pytest.fixture
def no_blob_client():
    """Client with a model that has no Binary fields (blob routes not mounted)."""
    from autocrud.crud.route_templates.blob import BlobRouteTemplate

    crud = AutoCRUD()
    crud.add_model(FileHolder)
    app = FastAPI()
    crud.apply(app)

    # Force blob_store to None on the route template to trigger 501
    for tmpl in crud.route_templates:
        if isinstance(tmpl, BlobRouteTemplate) and tmpl.mounted:
            tmpl._blob_store = None
            break
    return TestClient(app)


class TestBlobStoreNotConfigured:
    def test_create_session_501(self, no_blob_client):
        resp = _create_session(no_blob_client)
        assert resp.status_code == 501

    def test_get_session_501(self, no_blob_client):
        resp = _get_session(no_blob_client, "fake-id")
        assert resp.status_code == 501

    def test_put_content_501(self, no_blob_client):
        resp = _put_content(no_blob_client, "fake-id")
        assert resp.status_code == 501

    def test_finalize_501(self, no_blob_client):
        resp = _finalize(no_blob_client, "fake-id")
        assert resp.status_code == 501

    def test_abort_501(self, no_blob_client):
        resp = _abort(no_blob_client, "fake-id")
        assert resp.status_code == 501


# ---------------------------------------------------------------------------
# Tests — native store raises non-NotImplementedError exception
# ---------------------------------------------------------------------------


class _ErrorBlobStore(_NativeBlobStore):
    """Blob store that raises ValueError on session methods."""

    def create_upload_session(self, **kw):
        raise ValueError("native error")

    def get_upload_session(self, upload_id):
        raise ValueError("native error")

    def upload_to_session(self, upload_id, data):
        raise ValueError("native error")

    def finalize_upload_session(self, upload_id):
        raise ValueError("native error")

    def abort_upload_session(self, upload_id):
        raise ValueError("native error")


@pytest.fixture
def error_native_client():
    from autocrud.crud.route_templates.blob import BlobRouteTemplate

    crud = AutoCRUD()
    crud.add_model(FileHolder)
    app = FastAPI()
    crud.apply(app)

    store = _ErrorBlobStore()
    for tmpl in crud.route_templates:
        if isinstance(tmpl, BlobRouteTemplate) and tmpl.mounted:
            tmpl._blob_store = store
            break
    return TestClient(app)


class TestNativeStoreError:
    def test_create_session_error(self, error_native_client):
        resp = _create_session(error_native_client)
        assert resp.status_code == 400

    def test_get_session_error(self, error_native_client):
        resp = _get_session(error_native_client, "x")
        assert resp.status_code == 400

    def test_put_content_error(self, error_native_client):
        resp = _put_content(error_native_client, "x")
        assert resp.status_code == 409

    def test_finalize_error(self, error_native_client):
        resp = _finalize(error_native_client, "x")
        assert resp.status_code == 409

    def test_abort_error(self, error_native_client):
        resp = _abort(error_native_client, "x")
        assert resp.status_code == 409
