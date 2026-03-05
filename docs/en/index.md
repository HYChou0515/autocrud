# AutoCRUD

**AutoCRUD** is a **model-driven FastAPI automation framework** with built-in **versioning, permissions, and search**—so you can focus on business logic and ship faster.

Instead of writing repetitive CRUD endpoints, metadata handling, indexing, and validation logic, AutoCRUD generates and manages these automatically from your **domain model**.

---

## Why AutoCRUD?

### Focus on Business Logic

Developers only need to define **domain models** and **business logic**.

Common infrastructure concerns such as:

- metadata
- indexing
- events
- permissions
- version management

are automatically handled by the framework.

---

### Automatic FastAPI APIs

Register a model and AutoCRUD will generate:

- CRUD endpoints
- OpenAPI / Swagger documentation
- validation and schema handling

All with **zero boilerplate and zero manual wiring**.

---

### Built-in Version Control

AutoCRUD treats resources as **versioned objects**.

Features include:

- complete revision history
- draft editing without creating new revisions
- switching between revisions
- rollback and restore

This makes it suitable for:

- auditing
- change tracking
- draft workflows
- data recovery

---

### Highly Customizable

The framework is flexible and extensible.

You can customize:

- route naming conventions
- indexed fields
- event handlers
- permission checks
- storage backends

AutoCRUD adapts to your architecture instead of forcing one.

---

### Message Queue Integration

AutoCRUD includes **built-in asynchronous job processing**.

Jobs are treated as **resources**, meaning they benefit from:

- versioning
- status tracking
- retries
- audit history

This enables reliable background processing without adding a separate task framework.

---

# Quick Example

Define a model:

```python
from msgspec import Struct
from autocrud import AutoCRUD

class User(Struct):
    name: str
    email: str
```

Create a FastAPI app:

```python
from fastapi import FastAPI
from autocrud import AutoCRUD

app = FastAPI()

crud = AutoCRUD()
crud.add_model(User)
crud.apply(app)
```

Run the server:

```bash
uvicorn main:app --reload
```

AutoCRUD will automatically generate:

```
POST   /user
GET    /user
GET    /user/{resource_id}
PUT    /user/{resource_id}
PATCH  /user/{resource_id}
DELETE /user/{resource_id}
```

All endpoints come with **OpenAPI documentation**, **validation**, and **version tracking**.

---

# Core Concepts

To understand how AutoCRUD works internally:

* [Overview](concepts/overview.md)
* [Core Concepts](concepts/core-concepts.md)
* [Resource Lifecycle](concepts/resource-lifecycle.md)
* [Query System](concepts/query-system.md)
* [Schema](concepts/schema.md)

---

# Guides

Practical guides for using AutoCRUD in real projects:

* [Routes](howto/routes.md)
* [Relationships](howto/relationships.md)
* [Constraints](howto/constraints.md)
* [Migrations](howto/migrations.md)
* [Error Handling](howto/errors.md)

---

# Advanced Topics

* [Storage Backends](guides/storage.md)
* [Performance](guides/performance.md)

# Learn more

* [Why AutoCRUD exists](concepts/why-autocrud.md)
* [Architecture](concepts/architecture.md)
* [Data model](concepts/data-model.md)
* [Query system](concepts/query-system.md)


---

# Reference

* [Python API](reference/python_api.md)
* [Behavior Reference](reference/behavior.md)

---

# Project

* GitHub: [https://github.com/HYChou0515/autocrud](https://github.com/HYChou0515/autocrud)
* PyPI: [https://pypi.org/project/autocrud/](https://pypi.org/project/autocrud/)

---

If you want to quickly build **versioned APIs with FastAPI**, AutoCRUD provides the infrastructure so you can focus on what matters: **your business logic**.


