# Quickstart - Fast Demo

In this quickstart, we will build a small task tracker from a single schema.

With AutoCRUD, we will:

- define a schema
- generate persistence
- expose an API
- get a basic frontend
- add a small piece of business logic

## 1. Define the schema

We start with a single `Task` schema.

```python
from datetime import datetime
from typing import Literal

import msgspec


class Task(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["todo", "doing", "done"] = "todo"
    priority: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None
    due_date: datetime | None = None
    completed_at: datetime | None = None
```

This schema is enough for AutoCRUD to understand the resource shape, form fields, and API payloads.

## 2. Create the app

Register the schema as a resource.

```python continuation
from autocrud import crud, Schema
from fastapi import FastAPI

crud.add_model(Schema(Task, "v1"))
app = FastAPI()
crud.apply(app)

```

Once registered, AutoCRUD can generate persistence, CRUD API endpoints, and a basic frontend.

## 3. Run the server

Start the development server:

```bash
uvicorn main:server --reload
```

Then open the generated UI in your browser.

## 4. Create your first task

Create a task through the generated API:

```bash
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Write quickstart",
    "priority": "high",
    "assignee": "alice"
  }'
```

List tasks:

```bash
curl http://127.0.0.1:8000/tasks
```

## 5. Open the generated frontend

In the generated frontend, you can:

* browse tasks in a list view
* inspect a task in a detail view
* create and edit tasks with a generated form

The UI is derived from the schema, so fields like `status`, `priority`, and `due_date` are reflected automatically.

## 6. Add business rules

Schemas define structure, but real applications also need business rules.

For this example, we add three rules:

* `title` must not be empty
* high-priority tasks must have an assignee
* when a task becomes `done`, set `completed_at` automatically

```python
from datetime import datetime, timezone


def validate_and_finalize_task(new: Task, old: Task | None = None) -> Task:
    if not new.title.strip():
        raise ValueError("title must not be empty")

    if new.priority == "high" and not new.assignee:
        raise ValueError("high priority tasks must have an assignee")

    if new.status == "done" and new.completed_at is None:
        new = Task(
            title=new.title,
            description=new.description,
            status=new.status,
            priority=new.priority,
            assignee=new.assignee,
            due_date=new.due_date,
            completed_at=datetime.now(timezone.utc),
        )

    return new
```

Register the rule with the resource:

```python
app.resource(
    "tasks",
    schema=Task,
    before_save=validate_and_finalize_task,
)
```

Now your generated CRUD app includes both schema-driven structure and application-specific logic.

## 7. What’s next

From here, you can explore:

* relationships between resources
* revision history
* custom lifecycle hooks
* search and filtering
* custom routes
* frontend customization


Next Steps:

- [切換至production persistence](/guides/from-demo-to-production.md)
