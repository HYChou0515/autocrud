# Resource Lifecycle

This page explains how a resource changes over time in AutoCRUD.

It focuses on the practical lifecycle of a resource: **create, update, modify, switch, delete, restore, and migrate**.

If you are looking for terminology, read [Core Concepts](/autocrud/concepts/core-concepts) first. If you want the component view, see [Architecture](/autocrud/concepts/architecture).

---

## Why this matters

The lifecycle model is what gives AutoCRUD its built-in support for:

- revision history
- rollback and restore flows
- draft editing
- safe schema evolution over time

---

## Resource structure

Each resource consists of three conceptual layers:

| Layer | Description |
|------|-------------|
| Resource | Logical entity identified by `resource_id` |
| Revision | Version of the resource data |
| Metadata | Resource-level metadata (`meta`) |

The API can return these layers separately:

```text
GET /{model}/{resource_id}?returns=data,revision_info,meta
```

---

## 1. Create a resource

A resource is created using:

```text
POST /{model}
```

### ID generation

| Field | Behavior |
|------|----------|
| resource_id | generated UUID |
| revision_id | `{resource_id}:1` |
| parent_revision_id | `None` |

### Default status

The initial revision status is configured when the model is registered:

```python
crud.add_model(..., default_status=...)
```

If not configured, the default is:

```text
stable
```

Both `stable` and `draft` are supported. Use `draft` when you want an editing workflow that relies on in-place `modify` operations before promoting or replacing the current revision.

### Example

```text
resource_id = 550e8400-e29b-41d4-a716-446655440000
revision_id = 550e8400-e29b-41d4-a716-446655440000:1
```

Revision graph after creation:

```text
r1 (HEAD)
```

---

## 2. Understand the revision model

Revisions form a **directed graph similar to Git history**.

Normal updates append new revisions:

```text
r1 -> r2 -> r3 (HEAD)
```

Each revision stores:

- `revision_id`
- `parent_revision_id`
- `schema_version`
- `status`
- `created_time`
- `updated_time`

Revision metadata is stored in `RevisionInfo`.

---

## 3. Update creates a new revision

Update creates a **new revision**.

```text
PUT /{model}/{resource_id}
PATCH /{model}/{resource_id}
```

Behavior:

| Field | Behavior |
|------|----------|
| revision_id | new revision |
| parent_revision_id | previous HEAD |
| meta.created_time | unchanged |
| meta.updated_time | updated |
| info.created_time | new |
| info.updated_time | same as created_time |

Example:

```

r1 -> r2 -> r3 (HEAD)

```

---

## 4. Modify edits the current draft in place

Modify updates the **current revision in-place**.

```text
PUT /{model}/{resource_id}?mode=modify
PATCH /{model}/{resource_id}?mode=modify
```

Behavior:

| Field | Behavior |
|------|----------|
| revision_id | unchanged |
| parent_revision_id | unchanged |
| meta.created_time | unchanged |
| meta.updated_time | updated |
| info.created_time | unchanged |
| info.updated_time | updated |

This mode is typically used for **draft editing workflows**.

---

## 5. Revision status

Revisions have a status defined by:

```text
RevisionStatus
```

Current values:

```text
draft
stable
```

---

## 6. Switch the current revision

AutoCRUD allows changing which revision is considered **current (HEAD)**.

Example:

```text
r1 -> r2 -> r3 (HEAD)
```

Switch to `r2`:

```text
r1 -> r2 (HEAD) -> r3
```

If a new update occurs:

```text
r1 -> r2 -> r4 (HEAD)
      |-> r3
```

This behavior is similar to **Git branching from an older commit**.

---

## 7. Resource metadata

Resource-level metadata is stored separately from revision data.

Example fields:

```text
resource_id
current_revision_id
schema_version
created_time
updated_time
created_by
updated_by
is_deleted
```

Metadata is accessed via:

```text
GET /{model}/{resource_id}?returns=meta
```

---

## 8. Revision metadata

Revision-level metadata is stored in `RevisionInfo`.

Important fields:

```text
revision_id
parent_revision_id
schema_version
status
created_time
updated_time
created_by
updated_by
data_hash
```

Accessed via:

```text
GET /{model}/{resource_id}?returns=revision_info
```

---

## 9. Soft delete and restore

AutoCRUD uses **soft deletion**.

```text
DELETE /{model}/{resource_id}
```

Behavior:

| Field | Behavior |
|------|----------|
| meta.is_deleted | set to True |
| meta.updated_time | updated |
| revisions | unchanged |

Deletion **does not create a new revision**.

Revision history remains intact.

---

A soft-deleted resource can be restored.

```text
POST /{model}/{resource_id}/restore
```

Behavior:

| Field | Behavior |
|------|----------|
| meta.is_deleted | set to False |
| meta.updated_time | updated |

No new revision is created.

---

## 10. Schema migration

Each revision stores a `schema_version`.

When reading a revision:

- AutoCRUD attempts to decode using the **current schema**
- If decoding fails, the error is ignored (not treated as 404)

Resources can be migrated explicitly using:

```python
# Migrate the current revision
resource_manager.migrate(resource_id)

# Migrate a specific (non-current) revision
resource_manager.migrate(resource_id, revision_id="item:abc:1")
```

Migration process (current revision):

1. read existing revision data
2. run migration logic
3. update revision schema_version
4. update resource meta schema_version
5. write migrated data back

Migration process (specific revision):

1. locate the revision's actual schema_version in the resource store
2. read its data using the correct schema_version key
3. run migration logic
4. update the revision's schema_version
5. write migrated data back
6. **does not** update resource meta schema_version

> **Note**: `migrate()` only migrates one revision at a time. Old revisions
> that were created before a schema upgrade remain at their original
> schema_version until explicitly migrated.

## Switch and unmigrated revisions

When migration is configured, `switch()` checks whether the target revision
has been migrated to the resource's current schema_version.

- If the target revision is still at an older schema_version,
  `RevisionNotMigratedError` is raised.
- You must migrate the revision first before switching to it.

```python
from autocrud import RevisionNotMigratedError

try:
    resource_manager.switch(resource_id, old_revision_id)
except RevisionNotMigratedError:
    # Migrate the old revision first
    resource_manager.migrate(resource_id, revision_id=old_revision_id)
    resource_manager.switch(resource_id, old_revision_id)
```

Migration can also be executed across resources using **search-based migration APIs**.

---

## Summary

A typical lifecycle looks like this:

```text
create
↓
r1 (HEAD)
↓ update
r2 (HEAD)
↓ update
r3 (HEAD)

switch r2
↓
r2 (HEAD)

update
↓
r4 (HEAD)
```

Deletion does not remove revision history:

```text
meta.is_deleted = True
```

Restoration flips the deletion flag back:

```text
meta.is_deleted = False
```

Schema changes are handled through explicit migrations, and switching to older revisions may require those revisions to be migrated first.

---

## Read next

- [Data model](/autocrud/concepts/data-model)
- [Architecture](/autocrud/concepts/architecture)
- [Schema](/autocrud/concepts/schema)
- [Migrations](/autocrud/howto/migrations)
