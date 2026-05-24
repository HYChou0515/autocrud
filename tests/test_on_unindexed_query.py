"""``on_unindexed_query`` policy: a filter on a non-indexed field would match
nothing (the query silently under-returns). The policy makes that visible.

  - warn (default): emit a SpecStarWarning naming the field, run anyway.
  - error: raise UnindexedQueryError (HTTP 400).

A field is "queryable" if it is a ResourceMeta attribute or a configured
indexed key; anything else can never appear in ``indexed_data``.
"""

import warnings

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import OnUnindexedQuery, SpecStar
from specstar.errors import SpecStarWarning, UnindexedQueryError
from specstar.query_types import (
    DataSearchCondition,
    DataSearchGroup,
    DataSearchLogicOperator,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)


class Doc(msgspec.Struct):
    name: str
    note: str = ""


def _eq(field: str, value: str = "x") -> ResourceMetaSearchQuery:
    return ResourceMetaSearchQuery(
        data_conditions=[
            DataSearchCondition(
                field_path=field, operator=DataSearchOperator.equals, value=value
            )
        ]
    )


def _mgr(policy: OnUnindexedQuery | None = None):
    sp = SpecStar()
    kw: dict = {"default_user": "t"}
    if policy is not None:
        kw["on_unindexed_query"] = policy
    sp.configure(**kw)
    sp.add_model(Doc, name="doc", indexed_fields=[("name", str)])
    mgr = sp.get_resource_manager(Doc)
    mgr.create(Doc(name="a", note="hello"))
    return mgr


def _client(policy: OnUnindexedQuery | None = None) -> TestClient:
    sp = SpecStar()
    kw: dict = {"default_user": "t"}
    if policy is not None:
        kw["on_unindexed_query"] = policy
    sp.configure(**kw)
    sp.add_model(Doc, name="doc", indexed_fields=[("name", str)])
    app = FastAPI()
    sp.apply(app)
    c = TestClient(app, raise_server_exceptions=False)
    c.post("/doc", json={"name": "a", "note": "hello"})
    return c


_NONINDEXED_PARAM = {
    "data_conditions": '[{"field_path": "note", "operator": "eq", "value": "x"}]'
}


def test_warn_is_default_on_nonindexed_field():
    mgr = _mgr()  # default policy
    with pytest.warns(SpecStarWarning, match="note"):
        results = mgr.search_resources(_eq("note"))
    # the query still runs — it just under-returns (note isn't indexed)
    assert results == []


def test_no_warning_on_indexed_field():
    mgr = _mgr()
    with warnings.catch_warnings():
        warnings.simplefilter("error", SpecStarWarning)
        results = mgr.search_resources(_eq("name", "a"))
    assert len(results) == 1  # indexed → really matches


def test_no_warning_on_resource_meta_attribute():
    mgr = _mgr()
    # created_by is a ResourceMeta attribute, queryable without an index
    with warnings.catch_warnings():
        warnings.simplefilter("error", SpecStarWarning)
        mgr.search_resources(_eq("created_by", "t"))


def test_error_policy_raises_on_nonindexed_field():
    mgr = _mgr(OnUnindexedQuery.error)
    with pytest.raises(UnindexedQueryError) as ei:
        mgr.search_resources(_eq("note"))
    assert ei.value.fields == ["note"]


def test_error_policy_also_guards_count_resources():
    mgr = _mgr(OnUnindexedQuery.error)
    with pytest.raises(UnindexedQueryError):
        mgr.count_resources(_eq("note"))


def test_nonindexed_field_inside_group_is_detected():
    mgr = _mgr(OnUnindexedQuery.error)
    q = ResourceMetaSearchQuery(
        conditions=[
            DataSearchGroup(
                operator=DataSearchLogicOperator.and_op,
                conditions=[
                    DataSearchCondition(
                        field_path="name",
                        operator=DataSearchOperator.equals,
                        value="a",
                    ),
                    DataSearchCondition(
                        field_path="note",
                        operator=DataSearchOperator.equals,
                        value="x",
                    ),
                ],
            )
        ]
    )
    with pytest.raises(UnindexedQueryError) as ei:
        mgr.search_resources(q)
    assert ei.value.fields == ["note"]  # only the non-indexed leaf is flagged


def test_http_error_policy_returns_400():
    c = _client(OnUnindexedQuery.error)
    r = c.get("/doc", params=_NONINDEXED_PARAM)
    assert r.status_code == 400


def test_http_warn_policy_stays_200_and_underreturns():
    # warn must not change the HTTP contract — still 200, just (wrongly) empty
    c = _client()
    r = c.get("/doc", params=_NONINDEXED_PARAM)
    assert r.status_code == 200
    assert r.json() == []
