"""Slice 5: list truncation is never silent.

``GET /{model}`` always returns an ``X-Has-More`` header (cheap, via a
limit+1 probe) and, opt-in via ``?with_total=true``, an ``X-Total-Count``
header. The body stays a bare JSON array (non-breaking). ``iter_all()`` pages
through everything programmatically so a full scan can never truncate.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar


class Item(msgspec.Struct):
    name: str


def _client_with(n: int):
    sp = SpecStar()
    sp.configure(default_user="t")
    app = FastAPI()
    sp.add_model(Schema(Item, "v1"))
    sp.apply(app)
    c = TestClient(app)
    for i in range(n):
        c.post("/item", json={"name": f"i{i}"})
    return sp, c


def test_has_more_header_true_when_truncated():
    _, c = _client_with(3)
    r = c.get("/item?limit=1")
    assert r.status_code == 200
    assert r.headers["X-Has-More"] == "true"
    assert len(r.json()) == 1


def test_has_more_header_false_when_all_returned():
    _, c = _client_with(3)
    r = c.get("/item?limit=10")
    assert r.headers["X-Has-More"] == "false"
    assert len(r.json()) == 3


def test_total_count_is_opt_in():
    _, c = _client_with(3)
    assert "X-Total-Count" not in c.get("/item?limit=1").headers
    r = c.get("/item?limit=1&with_total=true")
    assert r.headers["X-Total-Count"] == "3"
    assert r.headers["X-Has-More"] == "true"


def test_iter_all_yields_everything_without_truncation():
    sp, _ = _client_with(5)
    mgr = sp.get_resource_manager(Item)
    metas = list(mgr.iter_all(batch_size=2))
    assert len(metas) == 5


def test_list_resources_no_arg_lists_all():
    sp, _ = _client_with(3)
    mgr = sp.get_resource_manager(Item)
    assert len(mgr.list_resources()) == 3  # no query == list all


def test_search_resources_no_arg_returns_all():
    sp, _ = _client_with(3)
    mgr = sp.get_resource_manager(Item)
    assert len(mgr.search_resources()) == 3  # no query == search all


def test_count_resources_no_arg_counts_all():
    sp, _ = _client_with(3)
    mgr = sp.get_resource_manager(Item)
    assert mgr.count_resources() == 3  # no query == count all


def test_no_arg_is_equivalent_to_qb_all():
    from specstar import QB

    sp, _ = _client_with(3)
    mgr = sp.get_resource_manager(Item)
    assert len(mgr.search_resources()) == len(mgr.search_resources(QB.all()))
    assert mgr.count_resources() == mgr.count_resources(QB.all())
