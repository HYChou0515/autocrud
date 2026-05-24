"""Issue D: a `do(...)` builder must be accepted in `event_handlers=[...]`.

`do(fn).after(...)` returns a `SimpleEventHandlerBuilder` (a Sequence of
handlers). Passing it as a list item used to fail at request time with
`'SimpleEventHandlerBuilder' object has no attribute 'is_supported'`. It is now
flattened into its handlers.
"""

import msgspec
from fastapi import FastAPI
from fastapi.testclient import TestClient

from specstar import Schema, SpecStar
from specstar.events import do
from specstar.types import ResourceAction


class T(msgspec.Struct):
    name: str


def test_do_builder_accepted_in_event_handlers_list():
    calls = []
    sp = SpecStar()
    sp.configure(
        default_user="t",
        event_handlers=[do(lambda ctx: calls.append(1)).after(ResourceAction.create)],
    )
    app = FastAPI()
    sp.add_model(Schema(T, "v1"))
    sp.apply(app)
    c = TestClient(app)
    assert c.post("/t", json={"name": "x"}).status_code == 200
    assert calls == [1]  # the handler actually ran
