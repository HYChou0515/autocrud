"""`GET /{model}/export` returns raw bytes; `POST /{model}/import` accepts
them. The import endpoint takes either a multipart `file` field or — so that
`export | import` round-trips — a raw `application/octet-stream` body.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import SpecStar


class Widget(msgspec.Struct):
    name: str


def _app() -> TestClient:
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Widget, name="widget")
    app = FastAPI()
    sp.apply(app)
    return TestClient(app, raise_server_exceptions=False)


def test_export_then_import_raw_bytes_round_trips():
    src = _app()
    src.post("/widget", json={"name": "roundtrip"})
    archive = src.get("/widget/export").content

    dst = _app()
    r = dst.post(
        "/widget/import",
        content=archive,  # raw body, not multipart
        headers={"content-type": "application/octet-stream"},
    )
    assert r.status_code == 200, r.text
    assert len(dst.get("/widget").json()) == 1  # the resource landed


def test_import_still_accepts_multipart_file():
    src = _app()
    src.post("/widget", json={"name": "viaform"})
    archive = src.get("/widget/export").content

    dst = _app()
    r = dst.post("/widget/import", files={"file": ("dump.acbak", archive)})
    assert r.status_code == 200, r.text
    assert len(dst.get("/widget").json()) == 1
