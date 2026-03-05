# Design philosophy

AutoCRUD exists to solve a common problem in backend development:

> Most applications repeatedly reimplement the same infrastructure around data.

Developers spend a large amount of time writing code for:

- CRUD endpoints
- metadata handling
- validation
- version tracking
- permissions
- search and filtering
- background job management

Yet most of this logic is **not the application's business logic**.

AutoCRUD attempts to move this infrastructure into a reusable framework so developers can focus on the domain itself.

---

# The problem with traditional CRUD

In a typical FastAPI project, a resource might require:

- database models
- Pydantic schemas
- CRUD functions
- routers
- validation logic
- search filters
- pagination logic
- background jobs
- audit history

A simple entity often expands into multiple files:

```

models.py
schemas.py
crud.py
routes.py
services.py
filters.py
tasks.py

```

While flexible, this approach often leads to:

- duplicated patterns
- inconsistent APIs
- difficult version tracking
- complex migrations
- ad-hoc job processing

AutoCRUD approaches the problem differently.

---

# Model-driven architecture

AutoCRUD is built around a **model-driven design**.

Instead of building infrastructure around models manually, developers define a domain model once:

```python
class User(Struct):
    name: str
    email: str
```

The framework automatically derives:

* API routes
* validation
* storage
* indexing
* search
* revision history

This shifts development from:

```
build infrastructure → implement business logic
```

to:

```
define model → implement business logic
```

---

# Resource-first design

AutoCRUD treats application data as **resources**.

A resource is not just a row in a database table.

Instead, a resource is a **versioned entity with metadata**.

Conceptually:

```
Resource
 ├── ResourceMeta
 └── Revisions
       └── Data
```

This design enables built-in support for:

* audit history
* rollback
* draft workflows
* revision switching
* time-travel debugging

These capabilities normally require significant custom infrastructure.

---

# Versioning by default

Most CRUD systems treat updates as destructive operations:

```
old data → overwritten
```

AutoCRUD instead records **revisions**:

```
r1 → r2 → r3
```

This provides several advantages:

* full audit history
* easier debugging
* safer deployments
* better data recovery

The framework also supports **draft editing**:

* `update()` creates a new revision
* `modify()` edits the current revision in place (typically for drafts)

This makes it possible to support editorial workflows naturally.

---

# ResourceManager as the single interface

One core principle of AutoCRUD is:

> Developers should not need to interact with storage systems directly.

Instead, everything goes through the **ResourceManager**.

```
ResourceManager
    ↓
Storage
```

This ensures:

* consistent validation
* centralized permissions
* correct revision handling
* consistent event hooks

It also means developers never need to write:

* SQL queries
* S3 storage logic
* file system operations

The framework handles these details.

---

# Separation of metadata and data

AutoCRUD separates resource metadata from revision data.

```
ResourceManager
    ↓
IStorage
    ├── MetaStore
    └── RevisionStore
```

This allows:

* efficient search
* fast metadata queries
* immutable revision storage
* scalable storage backends

Binary data is handled separately through **blob stores**.

---

# Search as a first-class feature

Many frameworks treat search as an afterthought.

AutoCRUD instead treats search as a core capability.

Resources maintain an **indexed projection of their data**:

```
ResourceMeta.indexed_data
```

This allows search queries to run without scanning revision payloads.

Typical flow:

```
QueryBuilder
    ↓
ResourceManager.search()
    ↓
MetaStore.search()
```

The result is a simple but efficient search model.

---

# Jobs as resources

Background jobs are often managed by separate systems:

* Celery
* RQ
* Temporal
* custom task queues

AutoCRUD takes a different approach:

> Jobs are just another type of resource.

This means jobs automatically inherit:

* version history
* retry tracking
* status fields
* audit history

When a resource manager has a message queue configured, new jobs can automatically be queued:

```python
create()
    ↓
message_queue.put(resource_id)
```

This integrates asynchronous processing with the same data model.

---

# Storage independence

AutoCRUD does not require a specific database.

Storage is abstracted through `IStorage` and `StorageFactory`.

This allows deployments such as:

| Storage  | Meta        | Revision | Blob       |
| -------- | ----------- | -------- | ---------- |
| Memory   | memory      | memory   | memory     |
| Disk     | SQLite      | files    | filesystem |
| S3       | SQLite (S3) | S3       | S3         |
| Postgres | PostgreSQL  | S3       | S3         |

Developers can also implement custom storage backends.

This flexibility allows AutoCRUD to work in:

* local development environments
* single-node deployments
* cloud-native distributed systems

---

# The goal of AutoCRUD

AutoCRUD is designed to reduce the amount of infrastructure code developers need to write.

Instead of implementing the same patterns repeatedly, the framework provides a consistent system for:

* versioned resources
* search and indexing
* validation
* permissions
* background jobs
* storage abstraction

This allows developers to focus on the most important part of their application:

> the business logic.
