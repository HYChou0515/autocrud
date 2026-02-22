# AutoCRUD

[![Docs](https://img.shields.io/badge/Docs-Documentation-blue)](https://hychou0515.github.io/autocrud/)
[![Wizard](https://img.shields.io/badge/Wizard-Starter_Wizard-ff69b4)](https://hychou0515.github.io/autocrud/wizard/)
[![PyPI](https://img.shields.io/pypi/v/autocrud)](https://pypi.org/project/autocrud/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Automation-009688)](https://fastapi.tiangolo.com)
[![GraphQL](https://img.shields.io/badge/GraphQL-Supported-E10098?logo=graphql)](https://graphql.org/)
[![msgspec](https://img.shields.io/badge/msgspec-Supported-5e60ce)](https://github.com/jcrist/msgspec)
[![Versioning](https://img.shields.io/badge/Versioning-Built--in-blue)]()

<div style="padding:12px;border:1px solid #add3ff99;border-radius:8px;background: #add3ff33;">
  <strong>AutoCRUD is a model-driven automated FastAPI:</strong> built-in versioning, permissions, and search, focused on getting business logic to production quickly.
</div>

## ✨ Features

- 🧠 **Focus only on business and models**: Developers only need to focus on business logic and domain model schema; metadata, indexing, events, permissions, and other foundational capabilities are automatically handled by the framework.
- ⚙️ **Automated FastAPI**: Apply a model with one line of code to automatically generate CRUD routes and OpenAPI/Swagger—zero boilerplate, zero manual binding.
- 🗂️ **Versioning**: Native support for full revision history, draft in-place editing, revision switching and restore—ideal for auditing, rollback, and draft workflows.
- 🔧 **Highly customizable**: Flexible route naming, indexed fields, event handlers, and permission checks.
- 🏎️ **High performance**: Built on FastAPI + msgspec for low latency and high throughput.

## 🧙 Starter Wizard

Use the interactive **Starter Wizard** to generate a ready-to-run AutoCRUD project with your models, storage, and permissions configured — no boilerplate needed.

👉 [https://hychou0515.github.io/autocrud/wizard/](https://hychou0515.github.io/autocrud/wizard/)

## Feature Overview

| Feature | Description |
| :--- | :--- |
| ✅ Auto-generation (Schema → API/Storage) | `Schema as Infrastructure`: automatically generates routes, logic bindings, and storage mappings |
| ✅ Versioning (Revision History) | Draft→Update / Stable→Append, complete parent revision chain |
| ✅ Migration | Functional Converter, Lazy Upgrade on Read + Save |
| ✅ Storage Architecture | Hybrid: Meta (SQL/Redis) + Payload (Object Store) + Blob |
| ✅ Scalability | Object Storage with decoupled indexing for horizontal scaling |
| ✅ Partial Update (PATCH) | Precise JSON Patch updates for speed and bandwidth efficiency |
| ✅ Partial Read | Skip unnecessary fields at msgspec decode time for speed and bandwidth efficiency |
| ✅ GraphQL Integration | Auto-generated Strawberry GraphQL Endpoint |
| ✅ Blob Optimization | BlobStore deduplication and lazy loading |
| ✅ Permissions | Three-tier RBAC (Global / Model / Resource) and custom checkers |
| ✅ Event Hooks | Customizable Before / After / OnSuccess / OnError for every operation |
| ✅ Route Templates | Standard CRUD plus plug-in custom endpoints |
| ✅ Search & Index | Meta Store provides efficient filtering, sorting, pagination, and complex queries |
| ✅ Audit / Logging | Post-event audit records and review workflows |
| ✅ Message Queue | Built-in async job processing; manage Jobs as resources with versioning and states |

## Installation

```
pip install autocrud
```

**Optional Dependencies**

For **S3** storage support:

```
pip install "autocrud[s3]"
```

For **BlobStore automatic Content-Type detection**:

```
pip install "autocrud[magic]"
```

`autocrud[magic]` depends on `python-magic`.

* **Linux**: Ensure `libmagic` is installed (e.g., on Ubuntu run `sudo apt-get install libmagic1`).
* **Other OS**: See the [python-magic installation guide](https://github.com/ahupp/python-magic#installation).

## Documentation

https://hychou0515.github.io/autocrud/

## AutoCRUD Web Generator

[`autocrud-web-generator`](https://www.npmjs.com/package/autocrud-web-generator) turns your AutoCRUD backend into a fully functional React admin interface in seconds — no frontend boilerplate, no manual wiring.

Point the generator at your running API and it produces:

- **TypeScript types** derived from OpenAPI schemas
- **Axios API clients** — one per resource, ready to use
- **List pages** with server-side pagination, sorting, and search
- **Create pages** with auto-generated forms and Zod validation
- **Detail pages** including full revision history browsing
- **Dashboard** with live resource counts

The output is a standalone [Vite](https://vitejs.dev/) + [React](https://react.dev/) + [Mantine](https://mantine.dev/) + [TanStack Router](https://tanstack.com/router) project — not a thin shell. You own the generated code and can customize it freely.

**Quick start** (backend must be running at `http://localhost:8000`):

```bash
npm install -g autocrud-web-generator
autocrud-web init my-app
cd my-app && pnpm install
pnpm generate --url http://localhost:8000
pnpm dev
```

See the [generator README](web/generator/README.md) for full CLI options and customization guide.

## Your First API

```python
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

class TodoList(Struct):
    items: list[TodoItem]
    notes: str

# Create AutoCRUD
crud = AutoCRUD()
crud.add_model(TodoItem)
crud.add_model(TodoList)

app = FastAPI()
crud.apply(app)
crud.openapi(app)

uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
```

## Auto-generated CRUD Endpoints

- `POST /todo-item` - Create
- `GET /todo-item/{id}/data` - Read
- `PATCH /todo-item/{id}` - JSON Patch update
- `DELETE /todo-item/{id}` - Soft delete
- `GET /todo-list/data` - List with search support
- *A dozen more auto endpoints*

➡️ *AutoCRUD User Guide*

## Operate Resources via ResourceManager

ResourceManager is the entry point for resource operations in AutoCRUD. It manages create, query, update, delete, and versioning of resources.

Its core is **versioning**: every `create/update/patch` generates a new `revision_id` (create new revision) and preserves full history; drafts (`draft`) can be repeatedly edited with `modify` (in-place, without creating a new revision), then switched to `stable` when confirmed. You can also list all revisions, read any revision, `switch` the current revision, or `restore` after a soft delete. Indexed queries support filtering, sorting, and pagination by metadata and data fields (indexed fields), making it ideal for auditing, rollback, and large-scale retrieval.

➡️ *ResourceManager Guide*

## 🚀 Quick Start

```python
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient
from autocrud import AutoCRUD
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

class TodoList(Struct):
    items: list[TodoItem]
    notes: str

# Create CRUD API
crud = AutoCRUD()
crud.add_model(TodoItem)
crud.add_model(TodoList)

app = FastAPI()
crud.apply(app)

# Test
client = TestClient(app)
resp = client.post("/todo-list", json={"items": [], "notes": "My todos"})
todo_id = resp.json()["resource_id"]

# Add an item using JSON Patch
client.patch(f"/todo-list/{todo_id}", json=[{
    "op": "add", 
    "path": "/items/-",
    "value": {
        "title": "Complete item",
        "completed": False,
        "due": (datetime.now() + timedelta(hours=1)).isoformat()
    }
}])

# Get the result
result = client.get(f"/todo-list/{todo_id}/data")
print(result.json())
```

**Start the development server:**

```bash
python -m fastapi dev main.py
```

Visit [http://localhost:8000/docs](http://localhost:8000/docs) to view the auto-generated API documentation.
