"""HTTP-level tests for vector search via the ``qb=`` query-builder param (#408).

Vector search was fully wired in the direct ResourceManager API and the object
QB (``QB['f'].cosine(q) < t``), but the string QB parser used by the HTTP
``qb=`` param rejected ``cosine``/``l2``/``ip`` (not in the whitelist), so every
such request 400'd. These tests drive the real HTTP search route and assert both
the list-of-floats form and the natural-language string form (server-side
encoder) work end-to-end.
"""

from typing import Annotated, Any

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar import SpecStar, Vector


def _stub_encoder(text: str) -> list[float]:
    # Natural-language queries map to a fixed direction so ordering is assertable.
    if text in ("what is foo?", "near_query"):
        return [1.0, 0.0]
    if text == "far_query":
        return [0.0, 1.0]
    return [0.5, 0.5]


class Doc(Struct):
    title: str
    embedding: Annotated[list[float], Vector(dim=2, encoder="stub")]


@pytest.fixture
def client() -> TestClient:
    app: FastAPI = FastAPI()
    router: APIRouter = APIRouter()
    spec: SpecStar = SpecStar()
    spec.configure(vector_encoders={"stub": _stub_encoder})
    spec.add_model(Doc)
    spec.apply(router)
    app.include_router(router)
    return TestClient(app)


@pytest.fixture
def sample_docs(client: TestClient) -> None:
    docs: list[dict[str, Any]] = [
        {"title": "aligned", "embedding": [1.0, 0.0]},
        {"title": "close", "embedding": [0.9, 0.1]},
        {"title": "opposed", "embedding": [0.0, 1.0]},
    ]
    for d in docs:
        resp = client.post("/doc", json=d)
        assert resp.status_code == 200, resp.text


# #408 core ask: natural-language string query resolved server-side via encoder.
def test_qb_cosine_string_query_over_http(
    client: TestClient, sample_docs: None
) -> None:
    resp = client.get(
        "/doc/data",
        params={"qb": "QB['embedding'].cosine('what is foo?') < 0.3"},
    )
    assert resp.status_code == 200, resp.text
    titles = sorted(d["title"] for d in resp.json())
    assert titles == ["aligned", "close"]  # "opposed" excluded by threshold


# List-of-floats form parses through the whitelist too.
def test_qb_cosine_float_list_over_http(client: TestClient, sample_docs: None) -> None:
    resp = client.get(
        "/doc/data",
        params={"qb": "QB['embedding'].cosine([1.0, 0.0]) < 0.3"},
    )
    assert resp.status_code == 200, resp.text
    titles = sorted(d["title"] for d in resp.json())
    assert titles == ["aligned", "close"]


# l2 and ip are reachable (were previously rejected as "Method not allowed").
@pytest.mark.parametrize("distance", ["l2", "ip"])
def test_qb_other_distances_reachable(
    client: TestClient, sample_docs: None, distance: str
) -> None:
    resp = client.get(
        "/doc/data",
        params={"qb": f"QB['embedding'].{distance}([1.0, 0.0]) < 5.0"},
    )
    assert resp.status_code == 200, resp.text


# Vector ranking via qb sort: nearest to the query comes first.
def test_qb_cosine_sort_over_http(client: TestClient, sample_docs: None) -> None:
    resp = client.get(
        "/doc/data",
        params={
            "qb": (
                "(QB['embedding'].cosine('what is foo?') < 2.0)"
                ".sort(QB['embedding'].cosine('what is foo?'))"
            ),
        },
    )
    assert resp.status_code == 200, resp.text
    titles = [d["title"] for d in resp.json()]
    assert titles == ["aligned", "close", "opposed"]
