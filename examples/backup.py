"""
To see run test http methods, run
```
python schema_upgrade.py
```
To run test for pydantic model, run
```
python schema_upgrade.py pydantic
```

Model type choices are
"msgspec", "dataclass", "typeddict"

## Note: migration is not supported for pydantic

"""

import shutil
import sys


from autocrud.crud.core import DiskStorageFactory

if len(sys.argv) >= 2:
    mode = sys.argv[1]
else:
    mode = "msgspec"

if mode not in (
    "msgspec",
    "dataclass",
    "typeddict",
    "pydantic",
):
    raise ValueError(f"Invalid mode: {mode}")

from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from fastapi import FastAPI

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

elif mode == "pydantic":
    from pydantic import BaseModel

    class User(BaseModel):
        name: str
        age: int

elif mode == "typeddict":
    from typing import TypedDict

    class User(TypedDict):
        name: str
        age: int


def apply():
    shutil.rmtree("_autocrud_test_resource_dir", ignore_errors=True)

    crud = AutoCRUD()
    storage_factory = DiskStorageFactory("_autocrud_test_resource_dir")
    crud.add_model(User, storage_factory=storage_factory)

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
