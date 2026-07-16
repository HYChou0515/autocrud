"""End-to-end: ``?qb=`` fuzzy / similarity over HTTP on a **non-Postgres** backend.

Because the reference backends compute pg_trgm ``word_similarity`` faithfully
(:mod:`specstar.util.trigram`), an HTTP request carrying a fuzzy QB expression
works on every backend — here a plain in-memory store, so this runs in CI with
no services. The Postgres path (and its GIN acceleration) is the sibling
``tests/test_postgres_qb_fuzzy_route.py``; the parser accepting ``.fuzzy`` /
``.similarity`` is pinned service-free in ``tests/test_qb_parser.py``.
"""

from typing import Annotated

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar import BackendBinding, BackendConfig, SpecStar, TrigramIndex


class Doc(Struct):
    # The TrigramIndex annotation is harmless on a non-Postgres backend — it is
    # simply ignored (no GIN), and fuzzy is computed by scan.
    title: Annotated[str, TrigramIndex()]
    tags: Annotated[list[str], TrigramIndex()]


@pytest.fixture
def client():
    app = FastAPI()
    router = APIRouter()
    spec = SpecStar(default_user="t")
    spec.configure(
        backend=BackendConfig(
            meta=BackendBinding(type="memory"),
            resource=BackendBinding(type="memory"),
            blob=BackendBinding(type="memory"),
        ),
    )
    spec.add_model(Doc, indexed_fields=[("title", str), ("tags", list[str])])
    spec.apply(router)
    app.include_router(router)
    return TestClient(app)


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
    # Same ranking Postgres gives: "molecular" is an exact word of the first
    # title (1.0), only partial in "small molecule" (0.7).
    titles = [d["title"] for d in r.json()]
    assert titles == ["molecular biology", "small molecule"]


def test_fuzzy_on_a_list_field_over_http(client: TestClient) -> None:
    _seed(client)
    r = client.get("/doc/data", params={"qb": "QB['tags'].fuzzy('capp')"})
    assert r.status_code == 200, r.text
    titles = [d["title"] for d in r.json()]
    assert titles == ["molecular biology"]  # its "capping" tag


def test_custom_threshold_over_http(client: TestClient) -> None:
    _seed(client)
    # "ol" ~ "capping"/"mol"/"ol" — loosen the cutoff so the fragment matches.
    r = client.get(
        "/doc/data", params={"qb": "QB['tags'].fuzzy('capor', threshold=0.3)"}
    )
    assert r.status_code == 200, r.text
    titles = [d["title"] for d in r.json()]
    assert titles == ["molecular biology"]  # "capping" tag, similarity 0.5 >= 0.3
