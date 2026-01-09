import datetime as dt
from msgspec import Struct
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autocrud import AutoCRUD
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.types import Binary


class UserWithImage(Struct):
    username: str
    avatar: Binary


def test_resource_manager_binary(tmp_path):
    storage_factory = DiskStorageFactory(tmp_path)
    # Use default_user to avoid context errors in API
    autocrud = AutoCRUD(storage_factory=storage_factory, default_user="test_user")
    autocrud.add_model(UserWithImage, name="users")
    manager = autocrud.get_resource_manager(UserWithImage)

    data = b"1234567890"
    res = UserWithImage(username="test", avatar=Binary(data=data))

    # Create with context
    now = dt.datetime.now(dt.timezone.utc)
    with manager.meta_provide(user="tester", now=now):
        info = manager.create(res)

        # Check if avatar.data is None in stored resource
        stored_res = manager.get(info.resource_id)

    assert stored_res.data.avatar.data is None
    assert stored_res.data.avatar.file_id is not None
    assert stored_res.data.avatar.size == 10

    # Check blob retrieval via manager
    blob = manager.get_blob(stored_res.data.avatar.file_id)
    assert blob == data

    # Check API blob retrieval
    app = FastAPI()
    autocrud.apply(app)
    client = TestClient(app)

    # The URL pattern is /users/{resource_id}/blobs/{file_id}
    # We rely on AutoCRUD's dependency injection which uses default_user="test_user"
    resp = client.get(
        f"/users/{info.resource_id}/blobs/{stored_res.data.avatar.file_id}"
    )
    assert resp.status_code == 200
    assert resp.content == data


def test_deduplication(tmp_path):
    storage_factory = DiskStorageFactory(tmp_path)
    autocrud = AutoCRUD(storage_factory=storage_factory, default_user="dedup_tester")
    autocrud.add_model(UserWithImage, name="users")
    manager = autocrud.get_resource_manager(UserWithImage)

    data = b"duplicate_content"
    res1 = UserWithImage(username="u1", avatar=Binary(data=data))
    res2 = UserWithImage(username="u2", avatar=Binary(data=data))

    now = dt.datetime.now(dt.timezone.utc)
    with manager.meta_provide(now=now):
        info1 = manager.create(res1)
        info2 = manager.create(res2)

        r1 = manager.get(info1.resource_id)
        r2 = manager.get(info2.resource_id)

    assert r1.data.avatar.file_id == r2.data.avatar.file_id

    # Count files in blob store
    # The blob store is at tmp_path / "_blobs" based on my AutoCRUD impl
    blob_dir = tmp_path / "_blobs"

    assert len(list(blob_dir.iterdir())) == 1
