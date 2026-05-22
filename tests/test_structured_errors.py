"""Tests for the structured_errors envelope (Item 38).

When ``SpecStar(structured_errors=True)``, every error response — both
SpecStar's domain mappings via ``to_http_exception`` and FastAPI's own
``RequestValidationError`` — comes back as
``{"detail": {"message": str, "code": str, ...extras}}`` so clients can
parse with one shape.

The default (``structured_errors=False``) keeps the historical mix
(plain strings / dict for unique constraint / FastAPI's error array).
"""

import msgspec
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.types import Unique
from typing import Annotated


class Note(msgspec.Struct):
    title: str


class UniqueNote(msgspec.Struct):
    title: Annotated[str, Unique()]


def _make_client(structured: bool, models=(Note,)) -> TestClient:
    sp = SpecStar(structured_errors=structured)
    sp.configure(default_user="t")
    app = FastAPI()
    for m in models:
        sp.add_model(Schema(m, "v1"))
    sp.apply(app)
    return TestClient(app)


# --- default off: shapes vary per endpoint --------------------------------


def test_default_404_detail_is_a_string():
    c = _make_client(structured=False)
    r = c.get("/note/nope")
    assert r.status_code == 404
    assert isinstance(r.json()["detail"], str)


def test_default_query_422_detail_is_fastapi_array():
    c = _make_client(structured=False)
    r = c.get("/note?limit=0")
    assert r.status_code == 422
    assert isinstance(r.json()["detail"], list)


# --- structured on: every shape is {message, code, ...} -------------------


def test_structured_404_is_envelope():
    c = _make_client(structured=True)
    r = c.get("/note/nope")
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "RESOURCE_NOT_FOUND"
    assert "nope" in detail["message"]


def test_structured_validation_error_is_envelope():
    c = _make_client(structured=True)
    r = c.post("/note", json={"wrong": "a"})  # missing required title
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == "VALIDATION_ERROR"
    assert isinstance(detail["message"], str)


def test_structured_query_validation_error_includes_field_errors():
    c = _make_client(structured=True)
    r = c.get("/note?limit=0")  # ge=1 fails
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert detail["code"] == "VALIDATION_ERROR"
    assert "errors" in detail
    assert any("limit" in err["loc"] for err in detail["errors"])


def test_structured_unique_constraint_keeps_field_info():
    c = _make_client(structured=True, models=(UniqueNote,))
    c.post("/unique-note", json={"title": "A"})
    r = c.post("/unique-note", json={"title": "A"})
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["code"] == "UNIQUE_CONSTRAINT"
    assert detail["field"] == "title"
    assert "conflicting_resource_id" in detail
    assert "message" in detail


@pytest.mark.parametrize(
    "url,expected_status,expected_code",
    [
        ("/note/nope", 404, "RESOURCE_NOT_FOUND"),
        ("/note?limit=-1", 422, "VALIDATION_ERROR"),
    ],
)
def test_structured_envelope_consistency(url, expected_status, expected_code):
    c = _make_client(structured=True)
    r = c.get(url)
    assert r.status_code == expected_status
    detail = r.json()["detail"]
    assert isinstance(detail, dict)
    assert detail["code"] == expected_code
    assert isinstance(detail["message"], str)
