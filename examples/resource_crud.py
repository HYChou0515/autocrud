"""To start dev server, run
```
python -m fastapi dev resource_crud.py
````

To run test http methods, run
```
python resource_crud.py
```

Model type choices are
"msgspec", "dataclass", "typeddict"

"""

import sys

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

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from autocrud import AutoCRUD

if mode == "msgspec":
    from msgspec import Struct

    class Product(Struct):
        name: str
        quantity: int
        price: int
        tags: list[str]

elif mode == "dataclass":
    from dataclasses import dataclass

    @dataclass
    class Product:
        name: str
        quantity: int
        price: int
        tags: list[str]

elif mode == "typeddict":
    from typing import TypedDict

    class Product(TypedDict):
        name: str
        quantity: int
        price: int
        tags: list[str]


crud = AutoCRUD()
crud.add_model(Product)

app = FastAPI()

crud.apply(app)
crud.openapi(app)


def test():
    try:
        import rich

        console = rich.console.Console()

        def print_section(s, *args, **kwargs):
            console.print(
                f"======{s}======",
                *args,
                style="red",
                **kwargs,
            )

        print_json = console.print_json
    except ImportError:
        print_section = print
        print_json = print

    client = TestClient(app)

    print_section("Add 3 products")
    client.post(
        "/product",
        json={"name": "Apple", "quantity": 10, "price": 100, "tags": ["fruit", "food"]},
    )
    dt2 = datetime.now()
    client.post(
        "/product",
        json={"name": "Banana", "quantity": 5, "price": 50, "tags": ["fruit", "food"]},
    )
    dt3 = datetime.now()
    client.post(
        "/product",
        json={"name": "Cherry", "quantity": 2, "price": 25, "tags": ["fruit", "food"]},
    )

    print_section("Search for products created within a range")
    resp = client.get(
        "/product/full",
        params={"created_time_end": dt3, "created_time_start": dt2},
    )
    print_json(resp.text)

    print_section("Get meta of Banana")
    banana = client.get(f"/product/{resp.json()[0]['meta']['resource_id']}/meta")
    print_json(banana.text)
    banana_resource_id = banana.json()["resource_id"]

    print_section("Use patch to update the product")
    resp = client.patch(
        f"/product/{banana_resource_id}",
        json=[
            {"op": "replace", "path": "/quantity", "value": 20},
            {"op": "add", "path": "/tags/-", "value": "snack"},
            {"op": "move", "from": "/tags/0", "path": "/tags/-"},
            {"op": "remove", "path": "/tags/0"},
        ],
    )
    print_json(resp.text)

    print_section("Use also use put to update the product")
    resp = client.put(
        f"/product/{banana_resource_id}",
        json={"name": "Banana", "quantity": 5, "price": 250, "tags": ["fruit", "food"]},
    )
    print_json(resp.text)

    new_banana = client.get(f"/product/{banana_resource_id}/data")
    print_json(new_banana.text)

    print_section("Switch back to the previous revision.")
    client.post(
        f"/product/{banana_resource_id}/switch/{banana.json()['current_revision_id']}",
    )
    banana = client.get(f"/product/{banana_resource_id}/data")
    print_json(banana.text)

    print_section("Delete the product")
    client.delete(f"/product/{banana_resource_id}")
    resp = client.get(f"/product/{banana_resource_id}/data")
    print_json(resp.text)

    print_section("Search for the deleted product")
    resp = client.get("/product/meta", params={"is_deleted": True})
    print_json(resp.text)
    console.print(f"This is the same as {banana_resource_id=}")

    print_section("Restore the deleted product")
    resp = client.post(
        f"/product/{banana_resource_id}/restore",
        params={"is_deleted": True},
    )
    print_json(resp.text)
    resp = client.get(f"/product/{banana_resource_id}/data")
    console.print("After restoring, the product comes back")
    print_json(resp.text)


if __name__ == "__main__":
    test()
