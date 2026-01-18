---
title: Create Your First API
description: Step-by-step guide build to a complete CRUD API from scratch
---

# Create Your First API

This guide walks you through building a fully featured Todo API, including Versioning, Search, and filtering capabilities.

## Project Structure

Recommended project structure:

```
my-todo-api/
├── main.py          # Application entry point
├── models.py        # Data model definitions
├── requirements.txt # Dependency list
└── .env            # Environment variables (optional)
```

## Step 1: Install Dependencies

Create `requirements.txt`:

```txt title="requirements.txt"
autocrud
fastapi
uvicorn[standard]
```

Install:

```bash
pip install -r requirements.txt
```

## Step 2: Define Data Models

Create `models.py`:

```python title="models.py"
from msgspec import Struct
from datetime import datetime

class TodoItem(Struct):
    """A single todo item"""
    title: str
    description: str = ""
    completed: bool = False
    priority: int = 0  # 0=Low, 1=Medium, 2=High
    due: datetime | None = None
    tags: list[str] = []

class TodoList(Struct):
    """Todo list (contains multiple items)"""
    name: str
    description: str = ""
    items: list[TodoItem] = []
    owner: str = "anonymous"
```

!!! tip "Tips for designing data models"
    - Use `msgspec.Struct` instead of Pydantic `BaseModel`
    - Provide default values for all optional fields
    - Use type hints to ensure data correctness
    - Take advantage of Python 3.10+ Union syntax (`str | None`)

## Step 3: Create an AutoCRUD Instance

Create `main.py`:

```python title="main.py"
from fastapi import FastAPI
from autocrud import AutoCRUD
from models import TodoItem, TodoList

# Create an AutoCRUD instance
crud = AutoCRUD()

# Register models
# Optional: specify which fields should be indexed to support search
crud.add_model(
    TodoItem,
    indexed_fields=[
        ("priority", int),
        ("completed", bool),
    ]
)

crud.add_model(
    TodoList,
    indexed_fields=[
        ("owner", str),
    ]
)

# Create the FastAPI app
app = FastAPI(
    title="Todo API",
    description="A todo API built with AutoCRUD",
    version="1.0.0"
)

# Apply CRUD routes to the app
crud.apply(app)
```

## Step 4: Start the Application

```bash
uvicorn main:app --reload
```

Visit [http://localhost:8000/docs](http://localhost:8000/docs) to view the API documentation.

## Step 5: Test the API

### Create a Todo List

```bash
curl -X POST "http://localhost:8000/todo-list" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Work Tasks",
    "description": "This week’s work list",
    "owner": "alice"
  }'
```

Response:

```json
{
  "resource_id": "todo-list_abc123",
  "revision_id": "rev_xyz789",
  "status": "stable",
  "created_at": "2025-01-17T10:00:00Z",
  "updated_at": "2025-01-17T10:00:00Z"
}
```

### Add Items Using JSON Patch

```bash
curl -X PATCH "http://localhost:8000/todo-list/todo-list_abc123" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "op": "add",
      "path": "/items/-",
      "value": {
        "title": "Finish AutoCRUD documentation",
        "description": "Update the quick start guide",
        "priority": 2,
        "completed": false,
        "due": "2025-01-20T18:00:00",
        "tags": ["Docs", "High Priority"]
      }
    }
  ]'
```

### Create a Single Todo Item

```bash
curl -X POST "http://localhost:8000/todo-item" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Learn msgspec",
    "priority": 1,
    "tags": ["Learning", "Tech"]
  }'
```

### Search and Filter

Search for all high-priority, incomplete items:

```bash
curl -X GET "http://localhost:8000/todo-item/data" \
  -H "Content-Type: application/json" \
  -d '{
    "conditions": {
      "and": [
        {
          "field": "priority",
          "operator": "eq",
          "value": 2
        },
        {
          "field": "completed",
          "operator": "eq",
          "value": false
        }
      ]
    },
    "limit": 10
  }'
```

!!! note "Indexed fields"
    Only fields specified as `indexed_fields` in `add_model()` can be used in search conditions.

### View Revision History

```bash
curl "http://localhost:8000/todo-list/todo-list_abc123/revisions"
```

## Advanced Features

### Add Permission Control

```python
from autocrud.permission import SimplePermissionChecker

# Create a simple permission checker
permission_checker = SimplePermissionChecker(
    allow_read=True,
    allow_create=True,
    allow_update=True,
    allow_delete=False  # Disallow delete
)

crud = AutoCRUD(permission_checker=permission_checker)
```

### Add Event Handlers

```python
from autocrud.types import EventContext, IEventHandler

class AuditEventHandler(IEventHandler):
    def after_create(self, ctx: EventContext, resource):
        print(f"Resource created: {resource.resource_id}")
    
    def after_update(self, ctx: EventContext, resource):
        print(f"Resource updated: {resource.resource_id}")

crud = AutoCRUD(event_handlers=[AuditEventHandler()])
```

### Custom Route Naming

```python
crud.add_model(
    TodoItem,
    route_name="tasks",  # Routes will be /tasks instead of /todo-item
    indexed_fields=[("priority", int)]
)
```

## FAQ

??? question "How do I modify an existing resource?"
    Use the `PATCH` endpoint with JSON Patch operations, or use `PUT` for a full update.

??? question "Can a resource be restored after deletion?"
    Yes! AutoCRUD uses soft delete. Restore it via the `POST /{model}/{id}/restore` endpoint.

??? question "How do I view all revisions of a resource?"
    Use the `GET /{model}/{id}/revisions` endpoint to retrieve the revision list.

??? question "Can I read only specific fields?"
    Yes! Use the `GET /{model}/{id}/partial` endpoint and pass the `fields` parameter.

## Next Steps

<div class="grid cards" markdown>

-   :material-shield-lock: __Permissions System__

    ---

    Learn how to implement advanced permission control

    [:octicons-arrow-right-24: Permissions Guide](../guides/permissions.md)

-   :material-history: __Versioning__

    ---

    Dive deeper into the versioning mechanism

    [:octicons-arrow-right-24: Versioning](../guides/versioning.md)

-   :material-magnify: __Search and Filter__

    ---

    Learn advanced search features

    [:octicons-arrow-right-24: Search Guide](../guides/search.md)

-   :material-puzzle: __ResourceManager__

    ---

    Operate directly with ResourceManager

    [:octicons-arrow-right-24: ResourceManager](../core-concepts/resource-manager.md)

</div>
