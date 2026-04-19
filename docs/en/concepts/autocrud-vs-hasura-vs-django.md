# AutoCRUD vs Hasura vs Django

These three tools can all help you build data-driven backends faster, but they solve the problem from very different starting points.

This page is a **decision guide** rather than a winner-takes-all comparison.

It compares:

- **AutoCRUD** – model-driven backend automation for FastAPI
- **Hasura** – database-driven GraphQL engine
- **Django** – full-stack web framework with ORM and admin interface

Use it to decide which tool best matches your architecture, team workflow, and product needs.

---

# Quick comparison

| If your starting point is... | Best fit | Why |
| --- | --- | --- |
| FastAPI + Python models + versioned data | **AutoCRUD** | You get generated APIs, revision history, search, and automation from a Python-first workflow. |
| PostgreSQL schema + GraphQL-first frontend | **Hasura** | It exposes GraphQL rapidly from an existing relational schema. |
| Full-stack web app with ORM and admin | **Django** | It provides the classic batteries-included web stack. |

## Feature comparison

| Feature | AutoCRUD | Hasura | Django |
| --- | --- | --- | --- |
| Primary model | Python models | Database schema | ORM models |
| REST API | ✅ | ⚠️ usually external | ✅ |
| GraphQL API | ✅ | ✅ | ⚠️ (via libraries) |
| Version history | ✅ built-in | ❌ | ❌ |
| Search engine | ✅ metadata indexing | SQL queries / filters | ORM queries |
| Storage | pluggable | PostgreSQL | relational databases |
| Background jobs | built-in resource jobs | external systems | Celery / external |
| Admin / UI | auto-generated UI | console only | Django admin |
| Target ecosystem | FastAPI | GraphQL | Django |

---

# AutoCRUD

AutoCRUD is a **model-driven backend platform built for FastAPI**.

Developers define data models in Python:

```python
class User(Struct):
    name: str
    email: str
```

From these models, AutoCRUD can automatically generate:

* REST APIs
* GraphQL APIs
* OpenAPI documentation
* search and filtering
* revision history
* background job processing
* admin UI generation

The goal is to allow developers to focus on **domain models and business logic**.

---

# Versioned resource model

Unlike typical CRUD frameworks, AutoCRUD treats application data as **versioned resources**.

```
Resource
 ├── ResourceMeta
 └── Revisions
       ├── r1
       ├── r2
       └── r3
```

Each update creates an immutable revision.

The active revision is stored in metadata:

```
ResourceMeta.current_revision_id
```

This provides built-in support for:

* audit history
* rollback
* draft workflows
* debugging

---

# Hasura

Hasura generates **GraphQL APIs directly from a PostgreSQL database**.

Architecture:

```
PostgreSQL
   ↓
Hasura Engine
   ↓
GraphQL API
```

Developers define tables and relationships in the database.

Hasura automatically generates:

* GraphQL queries
* GraphQL mutations
* subscriptions

Advantages:

* extremely fast API generation
* powerful GraphQL capabilities
* tight Postgres integration

Limitations:

* tightly coupled to PostgreSQL
* version history must be implemented manually
* business logic often implemented outside the API layer

Hasura works best for **database-driven GraphQL applications**.

---

# Django

Django is a full-stack web framework.

Architecture:

```
Django ORM
   ↓
Models
   ↓
Views / API
   ↓
Database
```

Developers define models using the Django ORM:

```python
class User(models.Model):
    name = models.CharField(...)
    email = models.EmailField(...)
```

Advantages:

* mature ecosystem
* built-in admin interface
* strong ORM
* batteries-included framework

Limitations:

* tightly coupled architecture
* APIs often require additional frameworks (Django REST Framework)
* version history requires custom implementation

Django is best suited for **full-stack web applications**.

---

# Architectural differences

## Data model

| Framework | Data model          |
| --------- | ------------------- |
| AutoCRUD  | versioned resources |
| Hasura    | relational tables   |
| Django    | ORM models          |

AutoCRUD explicitly models **revision history**.

---

## API generation

| Framework | API generation              |
| --------- | --------------------------- |
| AutoCRUD  | model-driven REST + GraphQL |
| Hasura    | schema-driven GraphQL       |
| Django    | manual views or DRF         |

AutoCRUD generates APIs from **Python models**.

Hasura generates APIs from **database schemas**.

---

## Storage flexibility

| Framework | Storage              |
| --------- | -------------------- |
| AutoCRUD  | pluggable            |
| Hasura    | PostgreSQL           |
| Django    | relational databases |

AutoCRUD supports multiple storage backends such as:

* memory
* disk
* S3
* PostgreSQL

---

# UI generation

AutoCRUD can generate a web interface directly from the API schema.

```
API
 ↓
UI generator
 ↓
admin dashboard
```

This allows rapid creation of internal tools and administrative systems.

Hasura provides a management console, while Django includes a built-in admin interface.

---

# When each is the better fit

## Choose AutoCRUD when

AutoCRUD is a strong choice when:

* you are building APIs with **FastAPI**
* you want **automatic REST and GraphQL APIs**
* version history and auditability matter
* infrastructure code should be minimized
* you want automatic admin UI generation

Typical use cases include:

* internal tools
* content systems
* configuration management
* job processing systems
* administrative APIs

## Choose Hasura when

Hasura is a strong choice when:

* your system is **database-first**
* you want **GraphQL APIs** quickly
* your data is primarily relational
* PostgreSQL is already the center of your design

## Choose Django when

Django is a strong choice when:

* you want a **full-stack framework**
* your application includes server-rendered pages
* you want a mature ecosystem and admin interface
* your team already works comfortably with Django conventions

---

# Summary

Each framework targets a different architecture.

| Framework | Best for |
| --------- | -------- |
| AutoCRUD  | model-driven FastAPI backends with built-in revision history |
| Hasura    | GraphQL over PostgreSQL |
| Django    | full-stack web applications |

In short:

```text
GraphQL over PostgreSQL -> Hasura
Full-stack web framework -> Django
FastAPI + model-driven APIs + revision history -> AutoCRUD
```

If you want to continue exploring AutoCRUD specifically, read [Why AutoCRUD exists](/autocrud/concepts/why-autocrud), [Overview](/autocrud/concepts/overview), or [Core Concepts](/autocrud/concepts/core-concepts).

