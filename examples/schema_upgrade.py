"""To see run test http methods, run
```
python schema_upgrade.py
```

Model type choices are
"msgspec", "dataclass", "typeddict"

"""

import shutil
import sys
from typing import IO


from autocrud.resource_manager.basic import Encoding, MsgspecSerializer
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.types import IMigration

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


def get_after_user():
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

    return User


def get_before_user():
    if mode == "msgspec":
        from msgspec import Struct

        class User(Struct):
            name: str
            income: float

    elif mode == "dataclass":
        from dataclasses import dataclass

        @dataclass
        class User:
            name: str
            income: float

    elif mode == "typeddict":
        from typing import TypedDict

        class User(TypedDict):
            name: str
            income: float

    return User


def apply(before_after):
    if before_after == "before":
        shutil.rmtree("_autocrud_test_resource_dir", ignore_errors=True)
    User = get_before_user() if before_after == "before" else get_after_user()

    crud = AutoCRUD(storage_factory=DiskStorageFactory("_autocrud_test_resource_dir"))

    class Migration(IMigration):
        @property
        def schema_version(self):
            return "v1"

        def migrate(self, data: IO[bytes], schema_version: str | None):
            BeforeUser = get_before_user()
            s = MsgspecSerializer(encoding=Encoding.json, resource_type=BeforeUser)
            od = s.decode(data.read())
            if mode == "typeddict":
                newd = User(
                    name=od["name"],
                    age=-1,
                )
            else:
                newd = User(
                    name=od.name,
                    age=-1,
                )
            return newd

    crud.add_model(
        User,
        migration=None if before_after == "before" else Migration(),
    )

    app = FastAPI()
    crud.apply(app)
    return app


def test_before():
    app = apply("before")
    client = TestClient(app)
    resp = client.post(
        "/user",
        json={"name": "John", "income": 100},
    )
    resp.raise_for_status()
    print(resp.json())
    resource_id = resp.json()["resource_id"]
    resp = client.get(f"/user/{resource_id}/data")


def test_after():
    app = apply("after")
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
