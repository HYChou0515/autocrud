"""Issue A: count and list disagree on undecodable rows — but not *silently*.

A row written under one struct can't be decoded after an incompatible,
same-version model change. ``list`` defensively skips it (reasonable), while
``count`` still counts it (meta is always decodable). That divergence is
acceptable; the bug is that it was *silent*. ``list_resources`` now logs a
warning naming how many rows it dropped, so operators can diagnose the gap.
"""

import logging

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.backend import DiskStorageFactory


def _spec(tmp_path):
    sp = SpecStar()
    sp.configure(storage_factory=DiskStorageFactory(str(tmp_path)), default_user="t")
    return sp


def test_list_warns_when_dropping_undecodable_rows(tmp_path, caplog):
    # 1. write a record under Item{name} @ v1
    class Item(msgspec.Struct):
        name: str

    sp1 = _spec(tmp_path)
    app1 = FastAPI()
    sp1.add_model(Schema(Item, "v1"))
    sp1.apply(app1)
    TestClient(app1).post("/item", json={"name": "foo"})

    # 2. read it back under an INCOMPATIBLE same-version Item{name, required_new}
    class Item(msgspec.Struct):  # noqa: F811 — intentional incompatible redefinition
        name: str
        required_new: str

    sp2 = _spec(tmp_path)
    app2 = FastAPI()
    sp2.add_model(Schema(Item, "v1"))
    sp2.apply(app2)
    c = TestClient(app2)

    assert c.get("/item/count").json() == 1  # meta still counts it
    with caplog.at_level(logging.WARNING, logger="specstar.resource_manager.core"):
        assert len(c.get("/item").json()) == 0  # undecodable → dropped from list
    # the divergence is no longer silent
    assert any(
        "decod" in r.getMessage().lower() or "skip" in r.getMessage().lower()
        for r in caplog.records
    ), f"expected a decode/skip warning, got: {[r.getMessage() for r in caplog.records]}"
