# Why AutoCRUD exists

Modern backend development repeatedly solves the same problem:

> Building infrastructure around application data.

In most FastAPI projects, developers implement the same patterns again and again.

Typical responsibilities include:

- CRUD APIs
- data validation
- pagination
- filtering and search
- version history
- permissions
- audit logs
- background jobs

However, most of this code is **not business logic**.

It is infrastructure.

AutoCRUD exists to remove this repetition.

---

# The problem with typical FastAPI projects

Consider a simple resource such as `User`.

A typical project structure might look like this:

```

models.py
schemas.py
crud.py
routes.py
services.py
filters.py
tasks.py

```

Even for simple resources, developers must write:

- route handlers
- database queries
- pagination logic
- search filters
- validation
- background jobs

Much of this code follows the same patterns across projects.

Over time, applications accumulate large amounts of infrastructure code that is not directly related to the domain.

---

# The idea: model-driven APIs

AutoCRUD introduces a **model-driven approach**.

Instead of building infrastructure manually, developers define a model once:

```python
class User(Struct):
    name: str
    email: str
```

From this model, the framework can automatically derive:

* CRUD routes
* OpenAPI documentation
* validation
* indexing
* search
* version history

This shifts development from:

```
build infrastructure → implement logic
```

to:

```
define model → implement logic
```

---

# Resources instead of rows

Traditional CRUD systems treat data as **rows in a database**.

AutoCRUD instead treats data as **resources with revision history**.

```
Resource
 ├── ResourceMeta
 └── Revisions
```

Each resource maintains a list of immutable revisions.

```
r1
r2
r3
```

The active revision is tracked by metadata.

```
ResourceMeta.current_revision_id
```

This design provides built-in support for:

* audit history
* rollback
* draft workflows
* debugging

without requiring additional infrastructure.

---

# ResourceManager as the single interface

AutoCRUD centralizes all operations through the **ResourceManager**.

Developers never interact directly with:

* SQL queries
* file storage
* object storage

Instead, everything flows through the manager:

```python
resource_manager.create(data)
resource_manager.get(resource_id)
resource_manager.update(resource_id, new_data)
```

The manager ensures that all operations consistently apply:

* validation
* metadata updates
* revision creation
* event handlers
* message queue integration

---

# Built-in search

Search functionality is frequently implemented separately in many applications.

AutoCRUD treats search as a core capability.

Searchable fields are extracted into metadata:

```
ResourceMeta.indexed_data
```

Example:

```
{
    "user.email": "alice@example.com"
}
```

Queries operate on metadata rather than scanning revision payloads.

This allows efficient filtering, sorting, and pagination.

---

# Jobs as resources

Background jobs are usually implemented with separate systems such as:

* Celery
* RQ
* custom job queues

AutoCRUD integrates jobs directly into the resource model.

A job is simply another resource type.

```
Job
 ├── status
 ├── retries
 └── errmsg
```

Creating a job automatically places it in the queue:

```
create()
 ↓
message_queue.put(resource_id)
```

Workers process jobs through the same ResourceManager interface.

---

# Storage independence

AutoCRUD abstracts persistence through `IStorage`.

This allows multiple storage strategies:

| Backend  | Meta       | Revision   | Blob       |
| -------- | ---------- | ---------- | ---------- |
| Memory   | memory     | memory     | memory     |
| Disk     | SQLite     | filesystem | filesystem |
| S3       | SQLite     | S3         | S3         |
| Postgres | PostgreSQL | S3         | S3         |

Because storage is abstracted, application code remains unchanged.

---

# What AutoCRUD is not

AutoCRUD is not designed to replace every backend architecture.

It is **not**:

* a full event sourcing system
* a workflow orchestration engine
* a distributed data platform

Instead, AutoCRUD focuses on one goal:

> Making model-driven APIs simple and consistent.

---

# When AutoCRUD is useful

AutoCRUD works well for applications where:

* APIs follow CRUD patterns
* version history is useful
* consistent API behavior is important
* developers want to focus on domain logic

Typical use cases include:

* internal tools
* administrative systems
* content management systems
* configuration management
* job processing systems

---

# The goal

AutoCRUD aims to reduce the amount of infrastructure code developers must write.

By combining:

* model-driven APIs
* versioned resources
* metadata indexing
* storage abstraction
* automatic route generation

developers can focus on what matters most:

> the business logic of their application.
