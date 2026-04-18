# Overview

AutoCRUD is a model-driven backend framework for FastAPI.

Its purpose is simple: define your data model once, then let the framework generate and manage the repetitive infrastructure around it.

---

## The mental model

If you are new to AutoCRUD, keep these three ideas in mind:

- a **resource** is the logical thing your application manages
- a **revision** is one version of that resource over time
- the **ResourceManager** is the component that performs the operations

That is enough to understand the rest of the system at a high level.

---

## What this means in practice

Instead of writing CRUD endpoints, validation glue, search filters, and version bookkeeping by hand, you typically:

1. define a Python model
2. register it with AutoCRUD
3. apply the generated routes to your FastAPI app

```python
from fastapi import FastAPI
from msgspec import Struct

from autocrud import crud


class User(Struct):
    name: str
    email: str


app = FastAPI()
crud.add_model(User)
crud.apply(app)
```

---

## What to read next

This page is intentionally brief.

Use the following pages depending on what you need:

- [Why AutoCRUD exists](/autocrud/concepts/why-autocrud) — what problems it is trying to solve
- [Core concepts](/autocrud/concepts/core-concepts) — a deeper explanation of resources, revisions, metadata, and managers
- [Architecture](/autocrud/concepts/architecture) — how the major pieces fit together
- [Resource lifecycle](/autocrud/concepts/resource-lifecycle) — how data evolves over time

---

## Summary

AutoCRUD gives you a stable model for building APIs around versioned resources, while keeping the operational details consistent across routes, storage, validation, and search.
