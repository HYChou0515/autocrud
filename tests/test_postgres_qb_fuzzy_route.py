"""End-to-end: ``?qb=`` fuzzy / similarity over HTTP against a real Postgres.

The parser accepting ``.fuzzy`` / ``.similarity`` is pinned service-free in
``tests/test_qb_parser.py``; the SQL is pinned in
``tests/test_trigram_index_marker.py``. This closes the loop: an HTTP request
carrying a fuzzy QB expression parses, builds a TrigramFuzzyCondition, runs on
Postgres, and comes back as rows.
"""

import uuid
from typing import Annotated

import psycopg2
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar import BackendBinding, BackendConfig, SpecStar, TrigramIndex

PG_DSN = "postgresql://admin:password@localhost:5432/your_database"


class Doc(Struct):
    title: Annotated[str, TrigramIndex()]
    tags: Annotated[list[str], TrigramIndex()]


@pytest.fixture
def client():
    table_prefix = f"trgm_route_{uuid.uuid4().hex[:8]}_"
    app = FastAPI()
    router = APIRouter()
    spec = SpecStar(default_user="t")
    spec.configure(
        backend=BackendConfig(
            meta=BackendBinding(
                type="postgres",
                options={"dsn": PG_DSN, "table_prefix": table_prefix},
            ),
            resource=BackendBinding(type="memory"),
            blob=BackendBinding(type="memory"),
        ),
    )
    spec.add_model(
        Doc,
        indexed_fields=[("title", str), ("tags", list[str])],
    )
    spec.apply(router)
    app.include_router(router)
    try:
        yield TestClient(app)
    finally:
        conn = psycopg2.connect(PG_DSN)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f'DROP TABLE IF EXISTS "{table_prefix}doc_meta" CASCADE')
        conn.close()


def _seed(client: TestClient) -> None:
    for title, tags in [
        ("molecular biology", ["mol", "capping"]),
        ("polymer chains", ["m4", "m40"]),
        ("small molecule", ["ol"]),
        ("unrelated", []),
    ]:
        r = client.post("/doc", json={"title": title, "tags": tags})
        assert r.status_code == 200, r.text


def test_fuzzy_filter_over_http(client: TestClient) -> None:
    _seed(client)
    r = client.get("/doc/data", params={"qb": "QB['title'].fuzzy('molec')"})
    assert r.status_code == 200, r.text
    titles = sorted(d["title"] for d in r.json())
    assert titles == ["molecular biology", "small molecule"]


def test_fuzzy_with_similarity_sort_over_http(client: TestClient) -> None:
    _seed(client)
    r = client.get(
        "/doc/data",
        params={
            "qb": (
                "QB['title'].fuzzy('molecular')"
                ".sort(QB['title'].similarity('molecular').desc())"
            )
        },
    )
    assert r.status_code == 200, r.text
    # "molecular" is an exact word of the first title (1.0) and only partial in
    # "small molecule" (0.7), so the ranking puts them in that order.
    titles = [d["title"] for d in r.json()]
    assert titles == ["molecular biology", "small molecule"]


def test_fuzzy_on_a_list_field_over_http(client: TestClient) -> None:
    _seed(client)
    r = client.get("/doc/data", params={"qb": "QB['tags'].fuzzy('capp')"})
    assert r.status_code == 200, r.text
    titles = [d["title"] for d in r.json()]
    assert titles == ["molecular biology"]  # its "capping" tag
