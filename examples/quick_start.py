"""To start dev server, run
```
python -m fastapi dev quick_start.py
````

To see run test http methods, run
```
python quick_start.py
```

Model type choices are
"msgspec", "dataclass", "typeddict"

"""

import sys
from datetime import datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from autocrud import AutoCRUD

if len(sys.argv) >= 2:
    mode = sys.argv[1]
else:
    mode = "msgspec"

if mode not in (
    "msgspec",
    "dataclass",
    "typeddict",
):
    raise ValueError(f"Invalid mode: {mode}")


if mode == "msgspec":
    from msgspec import Struct

    class TodoItem(Struct):
        title: str
        completed: bool
        due: datetime

    class TodoList(Struct):
        items: list[TodoItem]
        notes: str

elif mode == "dataclass":
    from dataclasses import dataclass

    @dataclass
    class TodoItem:
        title: str
        completed: bool
        due: datetime

    @dataclass
    class TodoList:
        items: list[TodoItem]
        notes: str


elif mode == "typeddict":
    from typing import TypedDict

    class TodoItem(TypedDict):
        title: str
        completed: bool
        due: datetime

    class TodoList(TypedDict):
        items: list[TodoItem]
        notes: str


crud = AutoCRUD()
crud.add_model(TodoItem)
crud.add_model(TodoList)

app = FastAPI()
crud.apply(app)


def test():
    client = TestClient(app)
    resp = client.post(
        "/todo-list",
        json={"items": [], "notes": "my todo"},
    )
    print(resp.json())
    todo_list_id = resp.json()["resource_id"]
    resp = client.patch(
        f"/todo-list/{todo_list_id}",
        json=[
            {
                "op": "add",
                "path": "/items/-",
                "value": {
                    "title": "Todo 1",
                    "completed": False,
                    "due": (datetime.now() + timedelta(hours=1)).isoformat(),
                },
            },
        ],
    )
    print(resp.json())
    resp = client.get(f"/todo-list/{todo_list_id}/data")
    print(resp.json())
    resp = client.patch(
        f"/todo-list/{todo_list_id}",
        json=[{"op": "replace", "path": "/items/0/completed", "value": True}],
    )
    resp = client.get(f"/todo-list/{todo_list_id}/data")
    print(resp.json())


if __name__ == "__main__":
    test()
