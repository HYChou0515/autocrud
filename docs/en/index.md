# SpecStar

**SpecStar** is a **spec-driven backend platform for FastAPI** with built-in **versioning, permissions, search, and API generation**.

What makes it different: every resource is a **versioned timeline by default** — rollback, audit, and time-travel come built in. If you don't need history, the same routes still work as plain CRUD.

It helps you spend less time wiring repetitive infrastructure and more time on your domain logic.

---

## What you get

With a Python model as the source of truth, SpecStar can generate and manage:

- REST APIs
- GraphQL APIs
- OpenAPI documentation
- revision history and rollback workflows
- search and query support
- permissions and event hooks
- admin UI generation from your API schema

---

## Choose your path

### I am new to SpecStar

Start here in order:

1. [Installation](/specstar/installation/)
2. [Quickstart](/specstar/quickstart/)
3. [Core Concepts](/specstar/concepts/core-concepts)
4. [How-to Guides](/specstar/howto/)

### I want to evaluate whether SpecStar fits my project

Read these pages first:

- [Why SpecStar](/specstar/concepts/why-specstar)
- [SpecStar vs Hasura vs Django](/specstar/concepts/specstar-vs-hasura-vs-django)
- [Architecture](/specstar/concepts/architecture)
- [From demo to production](/specstar/guides/from-demo-to-production)

### I already know which feature I need

Go directly to:

- [Routes](/specstar/howto/routes)
- [Relationships](/specstar/howto/relationships)
- [Permissions](/specstar/howto/permissions)
- [Query builder](/specstar/howto/query-builder)
- [Web UI](/specstar/howto/web-ui)
- [Backup and restore](/specstar/howto/backup-restore)

---

## Quick example

Define a model:

```python
from msgspec import Struct
from specstar import Schema

class User(Struct):
    name: str
    email: str
```

Create a FastAPI app:

```python
from fastapi import FastAPI
from specstar import spec

app = FastAPI()

spec.configure()
spec.add_model(Schema(User, "v1"))
spec.apply(app)
```

SpecStar will generate the standard CRUD surface, OpenAPI documentation, validation handling, and revision tracking.

---

## Documentation map

### Learn the basics

- [Quickstart](/specstar/quickstart/)
- [Examples](/specstar/examples/)
- [Overview](/specstar/concepts/overview)

### Understand the system design

- [Core Concepts](/specstar/concepts/core-concepts)
- [Resource Lifecycle](/specstar/concepts/resource-lifecycle)
- [Schema](/specstar/concepts/schema)
- [Query System](/specstar/concepts/query-system)

### Build real features

- [How-to Guides](/specstar/howto/)
- [Guides](/specstar/guides/)
- [Reference](/specstar/reference/)

---

## Project links

- GitHub: [https://github.com/HYChou0515/specstar](https://github.com/HYChou0515/specstar)
- PyPI: [https://pypi.org/project/specstar/](https://pypi.org/project/specstar/)

---

If you want to build **versioned APIs with FastAPI** and avoid repetitive boilerplate, SpecStar gives you a strong starting point without locking you into a full-stack monolith.


