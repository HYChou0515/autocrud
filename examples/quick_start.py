"""
To start dev server, run
```
python -m fastapi dev quick_start.py
````

To see run test http methods, run
```
python quick_start.py
```
"""

from datetime import datetime

from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from dataclasses import dataclass
from fastapi import FastAPI


@dataclass
class TodoItem:
    title: str
    completed: bool
    due: datetime


@dataclass
class TodoList:
    item_ids: list[str]
    notes: str


crud = AutoCRUD()
crud.add_model(TodoItem)
crud.add_model(TodoList)

app = FastAPI()
crud.apply(app)


def test():
    client = TestClient(app)
    resp = client.post(
        "/todo-item",
        json={"title": "Test Task", "completed": False, "due": "2023-10-01T00:00:00"},
    )
    print(resp.json())
    resp = client.post(
        "/todo-list",
        json={"item_ids": [resp.json()["resource_id"]], "notes": "Test Notes"},
    )
    print(resp.json())
    resp = client.get(f"/todo-list/{resp.json()['resource_id']}/data")
    print(resp.json())
    resp = client.get(f"/todo-item/{resp.json()['item_ids'][0]}/data")
    print(resp.json())


if __name__ == "__main__":
    test()
