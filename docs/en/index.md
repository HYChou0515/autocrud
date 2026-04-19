# AutoCRUD

**AutoCRUD** is a **model-driven FastAPI framework** with built-in **versioning, permissions, search, and API generation**.

It helps you spend less time wiring repetitive infrastructure and more time on your domain logic.

---

## What you get

With a Python model as the source of truth, AutoCRUD can generate and manage:

- REST APIs
- GraphQL APIs
- OpenAPI documentation
- revision history and rollback workflows
- search and query support
- permissions and event hooks
- admin UI generation from your API schema

---

## Choose your path

### I am new to AutoCRUD

Start here in order:

1. [Installation](/autocrud/installation/)
2. [Quickstart](/autocrud/quickstart/)
3. [Core Concepts](/autocrud/concepts/core-concepts)
4. [How-to Guides](/autocrud/howto/)

### I want to evaluate whether AutoCRUD fits my project

Read these pages first:

- [Why AutoCRUD](/autocrud/concepts/why-autocrud)
- [AutoCRUD vs Hasura vs Django](/autocrud/concepts/autocrud-vs-hasura-vs-django)
- [Architecture](/autocrud/concepts/architecture)
- [From demo to production](/autocrud/guides/from-demo-to-production)

### I already know which feature I need

Go directly to:

- [Routes](/autocrud/howto/routes)
- [Relationships](/autocrud/howto/relationships)
- [Permissions](/autocrud/howto/permissions)
- [Query builder](/autocrud/howto/query-builder)
- [Web UI](/autocrud/howto/web-ui)
- [Backup and restore](/autocrud/howto/backup-restore)

---

## Quick example

Define a model:

```python
from msgspec import Struct
from autocrud import Schema

class User(Struct):
    name: str
    email: str
```

Create a FastAPI app:

```python
from fastapi import FastAPI
from autocrud import crud

app = FastAPI()

crud.configure()
crud.add_model(Schema(User, "v1"))
crud.apply(app)
```

AutoCRUD will generate the standard CRUD surface, OpenAPI documentation, validation handling, and revision tracking.

---

## Documentation map

### Learn the basics

- [Quickstart](/autocrud/quickstart/)
- [Examples](/autocrud/examples/)
- [Overview](/autocrud/concepts/overview)

### Understand the system design

- [Core Concepts](/autocrud/concepts/core-concepts)
- [Resource Lifecycle](/autocrud/concepts/resource-lifecycle)
- [Schema](/autocrud/concepts/schema)
- [Query System](/autocrud/concepts/query-system)

### Build real features

- [How-to Guides](/autocrud/howto/)
- [Guides](/autocrud/guides/)
- [Reference](/autocrud/reference/)

---

## Project links

- GitHub: [https://github.com/HYChou0515/autocrud](https://github.com/HYChou0515/autocrud)
- PyPI: [https://pypi.org/project/autocrud/](https://pypi.org/project/autocrud/)

---

If you want to build **versioned APIs with FastAPI** and avoid repetitive boilerplate, AutoCRUD gives you a strong starting point without locking you into a full-stack monolith.


