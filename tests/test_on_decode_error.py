"""Configurable behavior when a stored row can't be decoded into the model.

`on_decode_error` policy (manager-level, so HTTP inherits it):
  - skip  (default): omit from list + warn; get degrades to error
  - error: raise ResourceDecodeError
  - raw  : return SearchedResource[UndecodableData] / Resource[UndecodableData]
"""

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.backend import DiskStorageFactory
from specstar.query_types import ResourceMetaSearchQuery


class ItemV1(msgspec.Struct):
    name: str


def _write_one(tmp_path):
    sp = SpecStar()
    sp.configure(storage_factory=DiskStorageFactory(str(tmp_path)), default_user="t")
    app = FastAPI()
    sp.add_model(Schema(ItemV1, "v1"), name="item")
    sp.apply(app)
    return TestClient(app).post("/item", json={"name": "foo"}).json()["resource_id"]


def _reader(tmp_path, on_decode_error):
    # incompatible, same-version model → persisted row can't decode
    class Item(msgspec.Struct):
        name: str
        required_new: str

    sp = SpecStar()
    sp.configure(
        storage_factory=DiskStorageFactory(str(tmp_path)),
        default_user="t",
        on_decode_error=on_decode_error,
    )
    sp.add_model(Schema(Item, "v1"), name="item")
    return sp.get_resource_manager(Item)


def _reader_client(tmp_path, on_decode_error):
    class Item(msgspec.Struct):
        name: str
        required_new: str

    sp = SpecStar()
    sp.configure(
        storage_factory=DiskStorageFactory(str(tmp_path)),
        default_user="t",
        on_decode_error=on_decode_error,
    )
    app = FastAPI()
    sp.add_model(Schema(Item, "v1"), name="item")
    sp.apply(app)
    return TestClient(app, raise_server_exceptions=False)


def test_error_policy_raises_on_undecodable_row(tmp_path):
    from specstar.errors import ResourceDecodeError

    _write_one(tmp_path)
    mgr = _reader(tmp_path, "error")
    with pytest.raises(ResourceDecodeError):
        mgr.list_resources(ResourceMetaSearchQuery())


def test_error_policy_http_returns_422(tmp_path):
    # HTTP must behave like the manager (it delegates). The stored entity is
    # unprocessable into the current schema → 422 (same status the raw
    # msgspec.ValidationError produced before, so this stays non-breaking).
    _write_one(tmp_path)
    c = _reader_client(tmp_path, "error")
    assert c.get("/item").status_code == 422


def test_raw_policy_returns_undecodable_data_with_dict(tmp_path):
    from specstar.types import UndecodableData

    _write_one(tmp_path)
    mgr = _reader(tmp_path, "raw")
    results = mgr.list_resources(ResourceMetaSearchQuery())
    assert len(results) == 1  # not dropped
    item = results[0]
    assert isinstance(item.data, UndecodableData)
    # same encoding → best-effort dict recovers the original payload
    assert item.data.data == {"name": "foo"}
    assert item.data.decode_error  # explains why the typed decode failed
    assert item.meta is not None  # envelope (meta/info) still intact


def test_raw_policy_encoding_change_falls_back_to_bytes(tmp_path):
    from specstar.resource_manager.basic import Encoding
    from specstar.types import UndecodableData

    _write_one(tmp_path)  # written as JSON (default)
    # same struct, but read with msgpack → JSON bytes can't parse to a dict
    sp = SpecStar()
    sp.configure(
        storage_factory=DiskStorageFactory(str(tmp_path)),
        default_user="t",
        on_decode_error="raw",
    )
    sp.add_model(Schema(ItemV1, "v1"), name="item", encoding=Encoding.msgpack)
    results = sp.get_resource_manager(ItemV1).list_resources(ResourceMetaSearchQuery())
    assert len(results) == 1
    d = results[0].data
    assert isinstance(d, UndecodableData)
    assert d.data is None  # couldn't even parse to a dict
    assert d.raw_base64 is not None  # but the original bytes are preserved


def test_raw_policy_http_returns_200_with_error_data(tmp_path):
    _write_one(tmp_path)
    c = _reader_client(tmp_path, "raw")
    r = c.get("/item")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert "decode_error" in body[0]["data"]  # data slot is an UndecodableData


def test_get_skip_degrades_to_error(tmp_path):
    # single get can't "skip" the only row requested → degrades to error
    from specstar.errors import ResourceDecodeError

    rid = _write_one(tmp_path)
    mgr = _reader(tmp_path, "skip")
    with pytest.raises(ResourceDecodeError):
        mgr.get(rid)


def test_get_raw_returns_undecodable_data(tmp_path):
    from specstar.types import UndecodableData

    rid = _write_one(tmp_path)
    res = _reader(tmp_path, "raw").get(rid)
    assert isinstance(res.data, UndecodableData)
    assert res.data.data == {"name": "foo"}
    assert res.info is not None
