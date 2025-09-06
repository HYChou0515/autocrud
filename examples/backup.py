"""To see run test http methods, run
```
python schema_upgrade.py
```

Model type choices are
"msgspec", "dataclass", "typeddict"

"""

import shutil
import sys

from autocrud.resource_manager.storage_factory import DiskStorageFactory

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

from fastapi import FastAPI
from fastapi.testclient import TestClient

from autocrud import AutoCRUD

if mode == "msgspec":
    from msgspec import Struct

    class User(Struct):
        name: str
        age: int

elif mode == "dataclass":
    from dataclasses import dataclass

    @dataclass
    class User:
        name: str
        age: int

elif mode == "typeddict":
    from typing import TypedDict

    class User(TypedDict):
        name: str
        age: int


def apply():
    shutil.rmtree("_autocrud_test_resource_dir", ignore_errors=True)

    crud = AutoCRUD(storage_factory=DiskStorageFactory("_autocrud_test_resource_dir"))
    crud.add_model(User)

    app = FastAPI()
    crud.apply(app)
    return app, crud


def test_before():
    app, crud = apply()
    client = TestClient(app)
    resp = client.post(
        "/user",
        json={"name": "John", "age": 42},
    )
    resp.raise_for_status()
    print(resp.json())
    resource_id = resp.json()["resource_id"]
    resp = client.get(f"/user/{resource_id}/data")
    with open("_autocrud.dump", "wb") as f:
        crud.dump(f)


def test_after():
    app, crud = apply()
    with open("_autocrud.dump", "rb") as f:
        crud.load(f)
    client = TestClient(app)
    resp = client.get(
        "/user/full",
    )
    resp.raise_for_status()
    print(resp.json())
    resource_id = resp.json()[0]["revision_info"]["resource_id"]
    resp = client.patch(
        f"/user/{resource_id}",
        json=[
            {"op": "replace", "path": "/age", "value": 10},
        ],
    )
    print(resp.json())
    resp = client.get(
        f"/user/{resource_id}/full",
    )
    print(resp.json())


if __name__ == "__main__":
    test_before()
    test_after()
