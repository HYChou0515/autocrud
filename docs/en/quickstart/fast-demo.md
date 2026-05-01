# Quickstart - Fast Demo

Build a full CRUD app with API, persistence, and UI — from a single schema.

⏱️ Estimated time: 3 minutes

In this quickstart, we will build a small issue tracker from a single schema.

With SpecStar, we will:

- define a schema
- generate persistence
- expose an API
- get a basic frontend
- add a small piece of business logic

## 1. Define the schema

We start with a single `Issue` schema.

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

This schema is enough for SpecStar to understand the resource shape, form fields, and API payloads.

Why `msgspec`? Check [here](/specstar/concepts/schema).

## 2. Create the app

Create a `main.py` and register the schema as a resource.

```python
from specstar import crud, Schema
from fastapi import FastAPI

app = FastAPI()

crud.configure()
crud.add_model(Schema(Issue, "v1"))

crud.apply(app)
```

Once registered, SpecStar can automatically:

- create persistence
- generate CRUD API endpoints
- generate a basic frontend

## 3. Run the server

Start the development server:

```bash
uvicorn main:app --reload
```

Then open:

- http://127.0.0.1:8000/docs
- http://127.0.0.1:8000/

You should see a working API and UI immediately.

## 4. Create your first issue

Create an issue through the generated API:

```bash
curl -X POST http://127.0.0.1:8000/issues \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quickstart page shows wrong example",
    "severity": "high",
    "assignee": "alice"
  }'
```

List issues:

```bash
curl http://127.0.0.1:8000/issues
```

## 5. Open the generated frontend

In the generated frontend, you can:

- browse issues in a list view
- inspect an issue in a detail view
- create and edit issues with a generated form

The UI is automatically generated from your schema, so fields like `status`, `severity`, and `due_date` are reflected without additional work.

## 6. Add business rules

Schemas define structure, but real applications also need business rules.

For this example, we add three rules:

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

To enable this rule, update the schema registration in **Step 2**:

```python
crud.add_model(
    Schema(Issue, "v1", validator=validate_and_finalize_issue),
)
```

After restarting the server, all create/update operations will go through this validation logic.

## 7. What’s next

You now have a working CRUD application.

From here, you can explore:

- relationships between resources
- revision history
- custom lifecycle hooks
- search and filtering
- custom routes
- frontend customization

Once this demo is working, one natural next step is backend setup. If you want your data to survive restarts, or you want real blob and job infrastructure, move from the demo defaults into a deliberate backend configuration.

Next Steps:

- [Set up your backend properly](/specstar/guides/backend-setup)
- [Move from demo to production](/specstar/guides/from-demo-to-production)
- [Generate or customize the Web UI](/specstar/howto/web-ui)


## Appendix: Full example (main.py)

Here is the complete example combining all the steps above:

```python
from datetime import datetime, timezone
from typing import Literal

import msgspec
from fastapi import FastAPI

from specstar import crud, Schema


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

crud.configure()
crud.add_model(
    Schema(Issue, "v1", validator=validate_and_finalize_issue),
)

crud.apply(app)
```

Run:

```bash
uvicorn main:app --reload
```