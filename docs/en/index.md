---
title: AutoCRUD
description: Model-driven automated FastAPI with built-in versioning, permissions, and search
---

# AutoCRUD

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __Quick Start__

    ---

    Define your data model and generate a complete CRUD API with one line of code

    [:octicons-arrow-right-24: Getting Started](getting-started/quickstart.md)

-   :material-cog-outline:{ .lg .middle } __Automate Everything__

    ---

    Automatically generate routes, permissions, versioning, search, and indexing

    [:octicons-arrow-right-24: Core Concepts](core-concepts/architecture.md)

-   :material-speedometer:{ .lg .middle } __High Performance__

    ---

    Built on FastAPI + msgspec for ultra-fast serialization and partial read/write

    [:octicons-arrow-right-24: Benchmarks](benchmarks/index.md)

-   :material-puzzle-outline:{ .lg .middle } __Highly Extensible__

    ---

    Flexible event system, custom routes, and hybrid storage strategies

    [:octicons-arrow-right-24: Advanced Features](advanced/graphql.md)

</div>

## Key Features

<div class="grid" markdown>

:material-brain:{ .lg .middle } __Focus on Business & Models Only__

Developers only need to focus on business logic and domain model schemas; foundational capabilities such as metadata, indexing, events, and permissions are automatically handled by the framework.

:material-cog-sync:{ .lg .middle } __Automated FastAPI__

Apply a model with one line of code to automatically generate CRUD routes and OpenAPI/Swagger—zero boilerplate, zero manual binding.

:material-file-tree:{ .lg .middle } __Versioning__

Native support for full revision history, draft in-place modification, revision switching, and restore—ideal for audit, rollback, and draft workflows.

:material-tune-variant:{ .lg .middle } __Highly Customizable__

Flexible route naming, indexed fields, event handlers, and permission checks.

:material-rocket-launch:{ .lg .middle } __High Performance__

Built on FastAPI + msgspec for low latency and high throughput.

:material-shield-check:{ .lg .middle } __Permissions System__

Three-tier RBAC (Global / Model / Resource) with custom checkers.

</div>

## Feature Overview

| Feature | Description |
| :--- | :--- |
| ✅ Auto-generation (Schema → API/Storage) | `Schema as Infrastructure`: automatically generates routes, logic bindings, and storage mappings |
| ✅ Versioning (Revision History) | Draft→Update / Stable→Append, complete parent revision chain |
| ✅ Migration | Functional Converter, Lazy Upgrade on Read + Save |
| ✅ Storage Architecture | Hybrid: Meta (SQL/Redis) + Payload (Object Store) + Blob |
| ✅ Scalability (Scale Out) | Object Storage with decoupled indexing for easy horizontal scaling |
| ✅ Partial Update (PATCH) | Precise updates with JSON Patch to improve speed and save bandwidth |
| ✅ Partial Read | Skip unnecessary fields during msgspec decoding to improve speed and save bandwidth |
| ✅ GraphQL Integration | Automatically generated Strawberry GraphQL endpoint |
| ✅ Blob Optimization | BlobStore deduplication and lazy loading |
| ✅ Permission Control | Three-tier RBAC (Global / Model / Resource) with custom checkers |
| ✅ Event Hooks | Customize Before / After / OnSuccess / OnError for every operation |
| ✅ Route Templates | Standard CRUD and plug-in custom endpoints |
| ✅ Search & Index | Meta Store provides efficient filtering, sorting, pagination, and complex queries |
| ✅ Audit / Logging | Supports post-event audit records and review workflows |
| ✅ Message Queue | Built-in async task processing; treat Jobs as resources with versioning and state management |

## Quick Example

```python
from datetime import datetime
from fastapi import FastAPI
from autocrud import AutoCRUD
from msgspec import Struct

class TodoItem(Struct):
    title: str
    completed: bool
    due: datetime

# Create AutoCRUD
crud = AutoCRUD()
crud.add_model(TodoItem)

app = FastAPI()
crud.apply(app)

# That's it! The following endpoints are auto-generated:
# - POST /todo-item - Create
# - GET /todo-item/{id}/data - Read
# - PATCH /todo-item/{id} - JSON Patch update
# - DELETE /todo-item/{id} - Soft delete
# - GET /todo-item/data - List search
# - Plus more than a dozen additional endpoints...
```

!!! tip "Start the development server"
    ```bash
    uv run fastapi dev main.py
    ```
    
    Visit [http://localhost:8000/docs](http://localhost:8000/docs) to view the auto-generated API documentation.

## Installation

=== "Basic Installation"

    ```bash
    pip install autocrud
    ```

=== "With S3 Support"

    ```bash
    pip install "autocrud[s3]"
    ```

=== "With Magic (Content-Type Detection)"

    ```bash
    pip install "autocrud[magic]"
    ```

!!! note "python-magic Dependency"
    `autocrud[magic]` depends on `python-magic`.
    
    - **Linux**: Ensure `libmagic` is installed (e.g., on Ubuntu run `sudo apt-get install libmagic1`).
    - **Other OS**: Refer to the [python-magic installation guide](https://github.com/ahupp/python-magic#installation).

## Next Steps

<div class="grid cards" markdown>

-   [:material-book-open-page-variant: Quick Start](getting-started/quickstart.md)
-   [:material-domain: Architecture Overview](core-concepts/architecture.md)
-   [:material-api: AutoCRUD Routes](core-concepts/auto-routes.md)
-   [:material-code-braces: Examples](examples/index.md)

</div>
