import datetime as dt
import json

import pytest
from msgspec import Struct

from specstar import SpecStar
from specstar.backend import (
    BackendBinding,
    BackendConfig,
    BackendProvider,
    ConnectionProfile,
    register_backend_provider,
)
from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.resource_manager.blob_store.simple import DiskBlobStore, MemoryBlobStore
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore


class User(Struct):
    name: str
    age: int


def test_configure_with_backend_config_and_json_file(tmp_path):
    config_path = tmp_path / "backend.json"
    config_path.write_text(
        json.dumps(
            {
                "version": 1,
                "connections": {
                    "local": {
                        "type": "disk",
                        "options": {"rootdir": str(tmp_path / "data")},
                    }
                },
                "meta": {"use": "local"},
                "resource": {"use": "local"},
                "blob": {"use": "local"},
                "mq": {"type": "simple", "options": {"max_retries": 1}},
            }
        )
    )

    spec = SpecStar(backend=config_path)

    assert isinstance(spec.blob_store, DiskBlobStore)
    assert isinstance(spec.message_queue_factory, SimpleMessageQueueFactory)

    spec.add_model(User)
    manager = spec.get_resource_manager(User)
    with manager.meta_provide(user="tester", now=dt.datetime.now()):
        info = manager.create(User(name="Alice", age=30))

    assert info.resource_id is not None


def test_backend_config_object_supports_shared_connections(tmp_path):
    backend = BackendConfig(
        connections={
            "local": ConnectionProfile(
                type="disk",
                options={"rootdir": str(tmp_path / "shared-data")},
            )
        },
        meta=BackendBinding(use="local"),
        resource=BackendBinding(use="local"),
        blob=BackendBinding(use="local"),
        mq=BackendBinding(type="simple", options={"max_retries": 2}),
    )

    spec = SpecStar()
    spec.configure(backend=backend)

    assert isinstance(spec.blob_store, DiskBlobStore)
    assert isinstance(spec.message_queue_factory, SimpleMessageQueueFactory)


def test_custom_backend_provider_can_be_registered():
    class CustomMemoryProvider(BackendProvider):
        type = "custom-memory"
        capabilities = frozenset({"meta", "resource", "blob"})

        def build_meta(self, *, model_name, options, defaults):
            return MemoryMetaStore()

        def build_resource(self, *, model_name, options, defaults):
            return MemoryResourceStore()

        def build_blob(self, *, options, defaults):
            return MemoryBlobStore()

    register_backend_provider(CustomMemoryProvider())

    spec = SpecStar(
        backend=BackendConfig(
            meta=BackendBinding(type="custom-memory"),
            resource=BackendBinding(type="custom-memory"),
            blob=BackendBinding(type="custom-memory"),
        )
    )

    assert isinstance(spec.blob_store, MemoryBlobStore)


def test_backend_config_rejects_unknown_connection():
    with pytest.raises(ValueError, match="unknown connection"):
        SpecStar(
            backend=BackendConfig(
                meta=BackendBinding(use="missing"),
                resource=BackendBinding(type="memory"),
            )
        )
