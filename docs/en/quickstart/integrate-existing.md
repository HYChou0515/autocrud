# Quickstart - Integrate with Existing Codebase

In this quickstart, we will show how to integrate AutoCRUD into an existing FastAPI codebase.

AutoCRUD is designed for incremental adoption.  
You can add it to your current system without rewriting your application.

---

## Requirements

AutoCRUD requires:

- Python 3.11+
- FastAPI 0.115+
- Pydantic 1.10.26+ (v2 is also supported)

If your project is already using FastAPI, integration is typically straightforward.

---

## When should you use this guide?

This guide is for you if:

- you already have a FastAPI service
- you don’t want to rewrite existing endpoints
- you want to gradually adopt AutoCRUD for new or existing resources

---

## What we will do

In this guide, we will:

- keep an existing FastAPI app
- add one AutoCRUD-managed resource
- expose CRUD endpoints alongside existing APIs
- keep the original endpoints unchanged

---

## 1. Start from an existing FastAPI app

Assume you already have a FastAPI application:

```python
from fastapi import FastAPI

app = FastAPI()


@app.get("/ping")
def ping():
    return {"message": "pong"}
```

Your app is already running and serving endpoints.

---

## 2. Add a schema for the resource you want to manage

You can introduce AutoCRUD by defining a schema for one resource.

In this example, we add an `Issue` resource:

```python
from datetime import datetime
from typing import Literal

import msgspec


class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
    severity: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None
```

This schema can be completely independent from your existing routes and handlers.

---

## 3. Register the schema with AutoCRUD

Register the resource with AutoCRUD:

```python
from autocrud import crud, Schema

crud.add_model(Schema(Issue, "v1"))
```

At this point, AutoCRUD knows about the resource, but it is not attached to your FastAPI app yet.

---

## 4. Apply AutoCRUD to your existing app

Now attach AutoCRUD to the existing FastAPI instance:

```python
crud.apply(app)
```

This will add CRUD routes for the registered resource.

Your existing endpoints are still there, and AutoCRUD adds new ones alongside them.  
AutoCRUD only adds new routes and does not modify your existing endpoints.

Routes are generated directly from model names:

```
Issue → /issue
```

A minimal integrated example looks like this:

```python
from datetime import datetime
from typing import Literal

import msgspec
from fastapi import FastAPI

from autocrud import crud, Schema
from autocrud.resource_manager import DiskStorageFactory


class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
    severity: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None


app = FastAPI()


@app.get("/ping")
def ping():
    return {"message": "pong"}


crud.configure(
    storage_factory=DiskStorageFactory("./data")
)
crud.add_model(Schema(Issue, "v1"))
crud.apply(app)
```

---

### Using APIRouter (recommended for existing projects)

If your application is structured with `APIRouter`, you can attach AutoCRUD to a router instead of the main app.

```python
from fastapi import APIRouter, FastAPI

from autocrud import crud, Schema

app = FastAPI()
router = APIRouter(prefix="/api")


@app.get("/ping")
def ping():
    return {"message": "pong"}


crud.configure()
crud.add_model(Schema(Issue, "v1"))
crud.apply(app, router=router)
```

When `router` is provided, `apply()` automatically:

1. Generates routes on the router
2. Calls `app.include_router(router)` to mount the router
3. Calls `openapi(app)` to generate the OpenAPI schema

This allows you to:

- group AutoCRUD routes under a prefix (e.g. `/api/issue`)
- keep your existing routing structure unchanged
- integrate AutoCRUD without modifying your main app layout

If no router is provided, AutoCRUD will attach routes directly to the app.

If you need to include the router yourself (e.g. with custom tags or dependencies), pass `auto_include=False`:

```python
crud.apply(app, router=router, auto_include=False)
app.include_router(router, tags=["my-custom-tag"])
crud.openapi(app)
```

---

## 5. Run the server

Start the development server:

```bash
uvicorn main:app --reload
```

Now your app serves both:

- your original endpoint: `/ping`
- AutoCRUD-generated endpoints: `/issue` or `/api/issue`

You can also open:

- http://127.0.0.1:8000/docs

You should see both your existing routes and AutoCRUD-generated routes.

---

## 6. Use both systems together

Your original route still works:

```bash
curl http://127.0.0.1:8000/ping
```

```json
{"message":"pong"}
```

Create an issue:

```bash
curl -X POST http://127.0.0.1:8000/issue \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Bug: API returns 500",
    "status": "open",
    "severity": "high",
    "assignee": "alice"
  }'
```

If using `APIRouter`:

```bash
curl -X POST http://127.0.0.1:8000/api/issue \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Bug: API returns 500",
    "status": "open",
    "severity": "high",
    "assignee": "alice"
  }'
```

List issues:

```bash
curl http://127.0.0.1:8000/issue
```

Or:

```bash
curl http://127.0.0.1:8000/api/issue
```

This shows that AutoCRUD can coexist with your current application instead of replacing it.

---

## 7. Add business rules incrementally

Once the resource is integrated, you can start adding application-specific logic.

For example:

- `title` must not be empty
- high-severity issues must have an assignee
- when an issue becomes `resolved`, set `resolved_at` automatically

```python
from datetime import datetime, timezone


def validate_and_finalize_issue(new: Issue, old: Issue | None = None) -> Issue:
    if not new.title.strip():
        raise ValueError("title must not be empty")

    if new.severity == "high" and not new.assignee:
        raise ValueError("high severity issues must have an assignee")

    if new.status == "resolved" and new.resolved_at is None:
        new = Issue(
            title=new.title,
            description=new.description,
            status=new.status,
            severity=new.severity,
            assignee=new.assignee,
            due_date=new.due_date,
            resolved_at=datetime.now(timezone.utc),
        )

    return new
```

To enable this rule, update the schema registration (validators are part of the schema):

```python
crud.add_model(
    Schema(Issue, "v1", validator=validate_and_finalize_issue),
)
```

---

## 8. Adopt AutoCRUD gradually

A common migration path:

- start with one resource
- keep existing endpoints unchanged
- let AutoCRUD manage new CRUD-heavy resources
- gradually move validation and lifecycle logic into schema-driven rules

You do not need to migrate your whole codebase at once.

---

## 9. Optional features

AutoCRUD also supports:

- generated Web UI
- job queue for background processing

See:

- [Web UI](/autocrud/howto/web-ui)
- [Job Queue](/autocrud/quickstart/job-queue)

---

## 10. What’s next

From here, you can explore:

- adding more resources
- revision history and versioning
- custom lifecycle hooks
- custom routes
- background processing with job queue

A common next step is backend setup so your integrated resources persist correctly outside a demo environment.

Next Steps:

- [Set up the backend for persistence, blobs, and jobs](/autocrud/guides/backend-setup)
- [Job Queue](/autocrud/quickstart/job-queue)
- [Fast Demo](/autocrud/quickstart/fast-demo)

---

## Appendix: Full example

```python
# main.py
from datetime import datetime, timezone
from typing import Literal

import msgspec
from fastapi import APIRouter, FastAPI

from autocrud import Schema, crud


class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
    severity: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None


def validate_and_finalize_issue(new: Issue, old: Issue | None = None) -> Issue:
    if not new.title.strip():
        raise ValueError("title must not be empty")

    if new.severity == "high" and not new.assignee:
        raise ValueError("high severity issues must have an assignee")

    if new.status == "resolved" and new.resolved_at is None:
        new = Issue(
            title=new.title,
            description=new.description,
            status=new.status,
            severity=new.severity,
            assignee=new.assignee,
            due_date=new.due_date,
            resolved_at=datetime.now(timezone.utc),
        )

    return new


app = FastAPI()
router = APIRouter(prefix="/api")


@app.get("/ping")
def ping():
    return {"message": "pong"}


crud.configure()
crud.add_model(
    Schema(Issue, "v1", validator=validate_and_finalize_issue),
)

crud.apply(app, router=router)
```
