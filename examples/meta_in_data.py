"""
To start dev server, run
```
python -m fastapi dev meta_in_data.py
````

To run test http methods, run
```
python meta_in_data.py
```

To run test for pydantic model, run
```
python meta_in_data.py pydantic
```

Model type choices are
"msgspec", "dataclass", "typeddict", "pydantic"

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
    "pydantic",
):
    raise ValueError(f"Invalid mode: {mode}")

from datetime import datetime

from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from fastapi import FastAPI

if mode == "msgspec":
    from msgspec import Struct

    class User(Struct):
        id: str
        name: str
        age: int
        title: str
        manager_id: str

elif mode == "dataclass":
    from dataclasses import dataclass

    @dataclass
    class User:
        id: str
        name: str
        age: int
        title: str
        manager_id: str
elif mode == "pydantic":
    from pydantic import BaseModel

    class User(BaseModel):
        id: str
        name: str
        age: int
        title: str
        manager_id: str

elif mode == "typeddict":
    from typing import TypedDict

    class User(TypedDict):
        id: str
        name: str
        age: int
        title: str
        manager_id: str


crud = AutoCRUD()
crud.add_model(User)

app = FastAPI()
crud.apply(app)

