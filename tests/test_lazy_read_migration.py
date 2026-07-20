"""Issue C: registered migrations are applied lazily on the read path.

Reading a row stored at an older schema version, under a model with a
registered ``step(...)`` to the current version, returns the *migrated* object
(so count/list/get agree). Storage is NOT rewritten — ``revision_info`` /
``meta`` honestly keep the *stored* version until an explicit ``migrate()``
persists the upgrade, and a one-time log warning flags the lazy migration.
"""

import logging

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.backend import DiskStorageFactory
from specstar.query_types import ResourceMetaSearchQuery


class ItemV1(msgspec.Struct):
    name: str
    qty: int


class Item(msgspec.Struct):  # v2: qty -> quantity, + required sku
    name: str
    quantity: int
    sku: str


def _v1_to_v2(old: ItemV1) -> Item:
    return Item(name=old.name, quantity=old.qty, sku=f"AUTO-{old.name}")


def _write_v1(tmp_path) -> str:
    sp = SpecStar()
    sp.configure(storage_factory=DiskStorageFactory(str(tmp_path)), default_user="t")
    app = FastAPI()
    sp.add_model(Schema(ItemV1, "v1"), name="item")
    sp.apply(app)
    return (
        TestClient(app)
        .post("/item", json={"name": "widget", "qty": 7})
        .json()["resource_id"]
    )


def _reader_v2(tmp_path):
    sp = SpecStar()
    sp.configure(storage_factory=DiskStorageFactory(str(tmp_path)), default_user="t")
    sp.add_model(
        Schema(Item, "v2").step("v1", _v1_to_v2, source_type=ItemV1), name="item"
    )
    return sp.get_resource_manager(Item)


def test_lazy_read_migration_applies_registered_step(tmp_path, caplog):
    _write_v1(tmp_path)
    mgr = _reader_v2(tmp_path)

    with caplog.at_level(logging.WARNING, logger="specstar.resource_manager.core"):
        results = mgr.list_resources(ResourceMetaSearchQuery())

    assert len(results) == 1  # migrated, not dropped → agrees with /count
    data = results[0].data
    assert data.quantity == 7 and data.sku == "AUTO-widget"  # migrated shape
    # honest: storage is untouched, revision_info still reports the stored version
    assert results[0].info.schema_version == "v1"
    # the "looks migrated but isn't persisted" gap is surfaced
    assert any("migration on read" in r.getMessage() for r in caplog.records), [
        r.getMessage() for r in caplog.records
    ]


def test_lazy_read_migration_single_get(tmp_path):
    rid = _write_v1(tmp_path)
    res = _reader_v2(tmp_path).get(rid)
    assert res.data.quantity == 7 and res.data.sku == "AUTO-widget"
    assert res.info.schema_version == "v1"  # honest


def test_lazy_read_migration_http_count_equals_list(tmp_path):
    _write_v1(tmp_path)
    sp = SpecStar()
    sp.configure(storage_factory=DiskStorageFactory(str(tmp_path)), default_user="t")
    app = FastAPI()
    sp.add_model(
        Schema(Item, "v2").step("v1", _v1_to_v2, source_type=ItemV1), name="item"
    )
    sp.apply(app)
    c = TestClient(app)
    assert c.get("/item/count").json() == 1
    body = c.get("/item").json()
    assert len(body) == 1  # list now agrees with count
    assert body[0]["data"]["sku"] == "AUTO-widget"
