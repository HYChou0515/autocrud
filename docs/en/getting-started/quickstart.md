---
title: Quick Start
description: Get started with AutoCRUD in 5 minutes
---

# Quick Start

This guide will walk you through building a complete CRUD API in 5 minutes.

## Step 1: Installation

```bash
pip install autocrud
```

## Step 2: Define the Data Model

Use `msgspec.Struct` to define your data model:

```python
from msgspec import Struct
from datetime import datetime

class TodoItem(Struct):
    title: str
    completed: bool = False
    due: datetime | None = None
```

!!! tip "Why msgspec?"
    AutoCRUD uses `msgspec` instead of Pydantic because it provides:
    
    - ⚡ Faster serialization/deserialization speed
    - 🎯 More precise type checking
    - 💾 Smaller memory footprint

## Step 3: Create an AutoCRUD Instance

```python
from autocrud import AutoCRUD

crud = AutoCRUD()
crud.add_model(TodoItem)
```

## Step 4: Integrate with FastAPI

```python
from fastapi import FastAPI

app = FastAPI()
crud.apply(app)
```

## Complete Example

Combine the steps above:

```python title="main.py"
from msgspec import Struct
from datetime import datetime
from fastapi import FastAPI
from autocrud import AutoCRUD

class TodoItem(Struct):
    title: str
    completed: bool = False
    due: datetime | None = None

# Create AutoCRUD
crud = AutoCRUD()
crud.add_model(TodoItem)

# Create FastAPI app
app = FastAPI(title="Todo API")
crud.apply(app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

## Start the Service

=== "Use uvicorn"

    ```bash
    uvicorn main:app --reload
    ```

=== "Use FastAPI CLI"

    ```bash
    fastapi dev main.py
    ```

=== "Use uv"

    ```bash
    uv run uvicorn main:app --reload
    ```

## Test the API

After starting the service, visit [http://localhost:8000/docs](http://localhost:8000/docs) to view the auto-generated Swagger UI.

### Create a Todo Item

```bash
curl -X POST "http://localhost:8000/todo-item" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Learn AutoCRUD",
    "completed": false,
    "due": "2025-01-20T12:00:00"
  }'
```

Response:

```json
{
  "resource_id": "todo-item_abc123",
  "revision_id": "rev_xyz789",
  "status": "stable",
  "created_at": "2025-01-17T10:30:00Z"
}
```

### Query a Todo Item

```bash
curl "http://localhost:8000/todo-item/todo-item_abc123/data"
```

### Update a Todo Item

Using the JSON Patch standard:

```bash
curl -X PATCH "http://localhost:8000/todo-item/todo-item_abc123" \
  -H "Content-Type: application/json" \
  -d '[
    {"op": "replace", "path": "/completed", "value": true}
  ]'
```

### List All Todo Items

```bash
curl "http://localhost:8000/todo-item/data"
```

## Auto-generated Endpoints

AutoCRUD auto-generates the following endpoints for `TodoItem`:

| Method | Path | Description |
|------|------|------|
| `POST` | `/todo-item` | Create resource |
| `GET` | `/todo-item/{id}/data` | Get resource payload |
| `GET` | `/todo-item/{id}` | Get resource metadata |
| `PATCH` | `/todo-item/{id}` | JSON Patch update |
| `PUT` | `/todo-item/{id}` | Full update |
| `DELETE` | `/todo-item/{id}` | Soft delete |
| `POST` | `/todo-item/{id}/restore` | Restore deleted resource |
| `GET` | `/todo-item/data` | List query & search |
| `GET` | `/todo-item/{id}/revisions` | Get revision history |
| `POST` | `/todo-item/{id}/switch` | Switch revision |

!!! info "More endpoints available"
    For a complete list of endpoints, see [AutoCRUD Routes](../core-concepts/auto-routes.md).

## Next Steps

<div class="grid cards" markdown>

-   :material-book-open-page-variant: __Learn More__

    ---

    Learn AutoCRUD's core concepts and architecture

    [:octicons-arrow-right-24: Architecture Overview](../core-concepts/architecture.md)

-   :material-code-braces: __More Examples__

    ---

    Explore advanced features such as permissions and versioning

    [:octicons-arrow-right-24: Examples](../examples/index.md)

-   :material-cog: __ResourceManager__

    ---

    Operate resources directly with ResourceManager

    [:octicons-arrow-right-24: ResourceManager](../core-concepts/resource-manager.md)

-   :material-tune: __Custom Configuration__

    ---

    Learn how to customize routes, permissions, and events

    [:octicons-arrow-right-24: Feature Guides](../guides/versioning.md)

</div>
