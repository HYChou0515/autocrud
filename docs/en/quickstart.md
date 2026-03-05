# Quickstart

This quickstart uses `DiskStorageFactory` as the **minimal viable** persistent backend.

## Install

```bash
pip install autocrud
```

## Minimal FastAPI app

```python
from pathlib import Path
from fastapi import FastAPI
from msgspec import Struct

from autocrud import crud
from autocrud.resource_manager.storage_factory import DiskStorageFactory

class User(Struct):
    name: str
    age: int

app = FastAPI()

# 1) configure once at startup (global instance pattern)
crud.configure(
    storage_factory=DiskStorageFactory(Path("./data")),
    model_naming="kebab",
)

# 2) register models
crud.add_model(User)

# 3) generate routes
crud.apply(app)
```

## What to check next

* Route generation and customization: `docs/howto/routes.md`
* Storage backends overview: `docs/guides/storage.md`
* Why msgspec Struct is used as schema: `docs/concepts/schema.md`

