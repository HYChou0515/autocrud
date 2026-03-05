# AutoCRUD vs Hasura vs Django

Several frameworks aim to simplify backend development by automatically generating APIs and infrastructure around data models.

This article compares three different approaches:

- **AutoCRUD** – model-driven backend platform for FastAPI
- **Hasura** – database-driven GraphQL engine
- **Django** – full-stack web framework with ORM and admin interface

Although they solve similar problems, they are built around very different architectural philosophies.

---

# Quick comparison

| Feature | AutoCRUD | Hasura | Django |
|---|---|---|---|
| Primary model | Python models | Database schema | ORM models |
| REST API | ✅ | ❌ | ✅ |
| GraphQL API | ✅ | ✅ | ⚠️ (via libraries) |
| Version history | ✅ built-in | ❌ | ❌ |
| Search engine | ✅ metadata indexing | SQL queries | ORM queries |
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

# When to choose AutoCRUD

AutoCRUD is a good choice when:

* you are building APIs with **FastAPI**
* you want **automatic REST and GraphQL APIs**
* version history is important
* infrastructure code should be minimized
* you want automatic admin UI generation

Typical use cases include:

* internal tools
* content systems
* configuration management
* job processing systems
* administrative APIs

---

# When to choose Hasura

Hasura is a good choice when:

* your system is **database-first**
* you want **GraphQL APIs**
* your data is primarily relational
* you want instant API generation from SQL schemas

---

# When to choose Django

Django is a good choice when:

* you want a **full-stack framework**
* your application includes server-rendered pages
* you want a mature ecosystem and admin interface

---

# Summary

Each framework targets a different architecture.

| Framework | Best for                              |
| --------- | ------------------------------------- |
| AutoCRUD  | model-driven FastAPI backend platform |
| Hasura    | GraphQL over PostgreSQL               |
| Django    | full-stack web applications           |

AutoCRUD focuses on enabling **model-driven APIs with built-in version history, search, and automation**.

```

---

# 我建議再補一個小 section（會更強）

在文件最後加：

```

# Decision guide

```

例如：

```

Do you want GraphQL over PostgreSQL?
→ Hasura

Do you want a full-stack web framework?
→ Django

Do you want model-driven APIs with FastAPI?
→ AutoCRUD
