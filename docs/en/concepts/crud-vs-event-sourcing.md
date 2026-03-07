# AutoCRUD vs Traditional CRUD vs Event Sourcing

Modern backend systems typically follow one of three data management models:

1. **Traditional CRUD systems**
2. **Event sourcing systems**
3. **Revision-based systems (AutoCRUD)**

Each approach solves different problems and introduces different trade-offs.

This article explains how they differ and when each approach is appropriate.

---

# Traditional CRUD

Most web applications use a traditional CRUD architecture.

In this model, application data is stored as **rows in a database table**, and updates overwrite existing data.

Example:

```

users table

id   name   email
1    Alice  [alice@example.com](mailto:alice@example.com)

```

Updating a user:

```

UPDATE users
SET name = "Alice Smith"
WHERE id = 1

```

The old value is lost unless additional audit infrastructure is implemented.

## Typical architecture

```

API layer
↓
Service layer
↓
ORM / SQL
↓
Database

```

Typical FastAPI structure:

```

models.py
schemas.py
crud.py
routes.py
services.py

```

Each resource requires significant boilerplate.

## Advantages

- simple mental model
- efficient storage
- easy to understand
- widely supported

## Limitations

- no built-in version history
- difficult to audit changes
- destructive updates
- rollback is hard
- search infrastructure often duplicated

Developers frequently add additional systems to compensate:

- audit tables
- history tables
- soft delete fields
- event logs
- job queues

Over time, this infrastructure becomes complex.

---

# Event sourcing

Event sourcing takes a completely different approach.

Instead of storing the current state of an entity, the system stores **a sequence of events**.

Example:

```

UserCreated
UserEmailChanged
UserNameUpdated
UserDeactivated

```

The current state is reconstructed by replaying events.

```

events
↓
replay
↓
current state

```

## Example event log

```

event_stream

1  UserCreated {name: "Alice"}
2  UserEmailChanged {email: "[alice@example.com](mailto:alice@example.com)"}
3  UserNameUpdated {name: "Alice Smith"}

```

State reconstruction:

```

state = replay(events)

```

## Advantages

- complete history
- perfect auditability
- time-travel debugging
- excellent for distributed systems

## Limitations

- complex mental model
- difficult queries
- event schema evolution is hard
- replay cost can grow over time
- infrastructure complexity

Event sourcing is often used in:

- financial systems
- distributed workflows
- high-reliability systems

But it is frequently overkill for typical application backends.

---

# AutoCRUD revision model

AutoCRUD uses a **revision-based resource model**.

Instead of overwriting data or storing events, AutoCRUD stores **immutable revisions**.

```

resource
↓
revisions

r1
r2
r3

```

Each revision stores the **complete resource state**.

The active version is determined by a pointer in the metadata.

```

ResourceMeta
├─ resource_id
└─ current_revision_id

```

Switching revisions simply updates this pointer.

```

current_revision_id = r2

```

Older revisions remain unchanged.

---

# Architecture

The architecture centers around the **ResourceManager**.

```

API
↓
ResourceManager
↓
IStorage
├─ MetaStore
└─ RevisionStore

```

Responsibilities:

| Component | Responsibility |
|---|---|
| ResourceManager | business operations |
| MetaStore | search + metadata |
| RevisionStore | immutable revision storage |

Binary files are stored separately in **BlobStore**.

---

# Revision lifecycle

Typical resource lifecycle:

```

create
↓
revision r1
↓
update
↓
revision r2
↓
update
↓
revision r3

```

Revisions are immutable.

```

r1  (immutable)
r2  (immutable)
r3  (immutable)

```

The current revision is tracked by metadata.

---

# Draft workflow

AutoCRUD supports a draft workflow.

```

draft → stable

```

Rules:

| Status | modify | update |
|------|------|------|
| draft | allowed | allowed |
| stable | not allowed | allowed |

This allows editing drafts without creating new revisions.

---

# Search model

AutoCRUD avoids scanning revision payloads.

Instead, searchable fields are extracted into metadata.

```

ResourceMeta
indexed_data

```

Example:

```

indexed_data = {
"user.email": "[alice@example.com](mailto:alice@example.com)"
}

```

Search flow:

```

QueryBuilder
↓
ResourceManager.search()
↓
MetaStore.search()

```

This allows efficient queries without loading full resource data.

---

# Jobs as resources

AutoCRUD treats background jobs as resources.

Example job model:

```

class Job:
status
retries
max_retries   # per-job override (None → queue default)
errmsg

```

Job execution flow:

```

create()
↓
message_queue.put(resource_id)

```

Workers process jobs via:

```

ResourceManager.start_consume()

```

This unifies job management with the same resource model.

---

# Storage independence

AutoCRUD separates storage through `IStorage`.

Example deployment options:

| Storage | Meta | Revision | Blob |
|---|---|---|---|
| Memory | memory | memory | memory |
| Disk | SQLite | files | filesystem |
| S3 | SQLite | S3 | S3 |
| Postgres | PostgreSQL | S3 | S3 |

This allows different storage strategies without changing application logic.

---

# Comparison

| Feature | Traditional CRUD | Event Sourcing | AutoCRUD |
|---|---|---|---|
| Data model | mutable rows | event log | immutable revisions |
| History | optional | built-in | built-in |
| Query complexity | simple | complex | simple |
| Infrastructure | low | high | moderate |
| Debugging | difficult | excellent | good |
| Rollback | manual | natural | simple |

---

# When to use each approach

## Use traditional CRUD when

- the application is small
- version history is unnecessary
- infrastructure simplicity is important

## Use event sourcing when

- full event history is required
- distributed systems are involved
- strict auditability is required

## Use AutoCRUD when

- version history is important
- APIs should be generated automatically
- developers want to focus on domain models
- search and indexing should be built-in

AutoCRUD is particularly well suited for **FastAPI-based backends** where rapid development and consistent APIs are important.

---

# Summary

Traditional CRUD focuses on **simplicity**.

Event sourcing focuses on **event history and distributed systems**.

AutoCRUD focuses on **model-driven APIs with built-in revision history**.

The goal is to remove repetitive infrastructure code and allow developers to focus on the domain logic of their applications.
