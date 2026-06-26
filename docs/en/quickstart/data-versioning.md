# Quickstart - Data Versioning

Instead of overwriting data in place, SpecStar keeps every change as a new revision.

In this quickstart, we will show how to use SpecStar resource revision control to keep change history in your application.

With SpecStar, each create, update, and delete operation can produce a new revision. This allows you to:

- keep a full history of changes
- inspect older versions of a resource
- implement soft delete without losing data
- build audit-friendly applications with minimal extra work

⏱️ Estimated time: 5 minutes

---

## 1. Define and register a resource

We start with a simple `Issue` resource.

```python
from datetime import datetime
from typing import Literal

import msgspec
from fastapi import FastAPI

from specstar import spec, Schema


class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
    severity: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None


app = FastAPI()

spec.configure(default_user="quickstart", default_now=datetime.utcnow)
spec.add_model(Schema(Issue, "v1"))
spec.apply(app)
```

> Programmatic `mgr.create(...)` / `update(...)` / `migrate(...)` / `switch(...)`
> calls need an **operation context** (current user + clock). The simplest way is
> to pass `default_user` and `default_now` to `spec.configure()` as shown above.
> Alternatively, wrap each call in `mgr.using(user=..., now=...)`. Without a
> context, manager calls raise `MissingOperationContextError`.

Then get the resource manager:

```python
mgr = spec.get_resource_manager(Issue)
```

---

## 2. Create the first revision

Each `create()` call creates the first revision of the resource.

```python
info = mgr.create(
    Issue(
        title="Search returns duplicate results",
        severity="high",
        assignee="alice",
    )
)
```

The returned `info` contains revision metadata:

```python
print(info.resource_id)
print(info.revision_id)
```

Example output:

```text
issue:549443b6-1edd-412c-a70e-ee1f90ffd639
issue:549443b6-1edd-412c-a70e-ee1f90ffd639:1
```

You can fetch the current version of the resource with:

```python
issue = mgr.get(info.resource_id)
print(issue.data)
```

---

## 3. Update the resource and create a new revision

Instead of overwriting the existing data, this creates a new revision.

```python
info_updated = mgr.update(
    info.resource_id,
    Issue(
        title="Search returns duplicate results",
        severity="high",
        assignee="bob",
        status="in_progress",
    ),
)
```

This produces a new revision:

```python
print(info_updated.revision_id)
```

Example output:

```text
issue:549443b6-1edd-412c-a70e-ee1f90ffd639:2
```

You can fetch both the latest version and an older revision:

```python
new_issue = mgr.get(info.resource_id)
old_issue = mgr.get(info.resource_id, revision_id=info.revision_id)

print(new_issue.data)
print(old_issue.data)
```

This makes it easy to compare current and historical states of the same resource.

---

## 4. List revision history

You can inspect the full revision history of a resource. `list_revisions()`
returns the revision **id strings**; use `get_revision_info()` to fetch the
metadata (created time, author, …) for each one:

```python
revision_ids = mgr.list_revisions(info.resource_id)

for revision_id in revision_ids:
    rev = mgr.get_revision_info(info.resource_id, revision_id=revision_id)
    print(rev.revision_id, rev.created_time, rev.created_by)
```

This is useful for:

- audit trails
- debugging changes
- showing a change timeline in your UI

---

## 5. Soft delete without losing history

Deleting a resource does not have to mean losing it forever.

The resource is not physically removed — a new revision marks it as deleted.
`delete()` returns the resource's `ResourceMeta` (now with `is_deleted=True`),
not a `RevisionInfo`:

```python
deleted_meta = mgr.delete(info.resource_id)
print(deleted_meta.is_deleted, deleted_meta.current_revision_id)
```

You can still inspect older revisions if needed. Reading any revision of a
soft-deleted resource requires `include_deleted=True` (the same flag
`get_meta()` accepts); without it `get()` raises `ResourceIsDeletedError`:

```python
old_issue = mgr.get(
    info.resource_id, revision_id=info.revision_id, include_deleted=True
)
print(old_issue.data)
```

And if your application allows it, you can restore the resource later.

---

## 6. Why this matters

With revision control built into the resource layer, you do not need to design a separate history system for every model.

You now get, by default:

- current state access
- historical revision lookup
- soft delete support
- a foundation for audit logs and rollback workflows

You never lose data — you only move forward through revisions.

---

## What’s next

If you plan to rely on revision history in a real deployment, backend setup is a natural follow-up so that history persists beyond a throwaway demo.

Next Steps:

- [Set up backend persistence and storage](/specstar/guides/backend-setup)
- [Handle schema evolution safely](/specstar/quickstart/schema-migration)
- [Prune old revisions to reclaim storage](/specstar/howto/prune-revisions)
- [Move from demo to production](/specstar/guides/from-demo-to-production)

---

## Appendix: Full example

```python
from datetime import datetime
from typing import Literal

import msgspec
from fastapi import FastAPI

from specstar import spec, Schema


class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
    severity: Literal["low", "medium", "high"] = "medium"
    assignee: str | None = None
    due_date: datetime | None = None
    resolved_at: datetime | None = None


app = FastAPI()

spec.configure()
spec.add_model(Schema(Issue, "v1"))
spec.apply(app)

mgr = spec.get_resource_manager(Issue)

info = mgr.create(
    Issue(
        title="Search returns duplicate results",
        severity="high",
        assignee="alice",
    )
)

print("resource_id:", info.resource_id)
print("revision_id:", info.revision_id)

info_updated = mgr.update(
    info.resource_id,
    Issue(
        title="Search returns duplicate results",
        severity="high",
        assignee="bob",
        status="in_progress",
    ),
)

print("updated revision_id:", info_updated.revision_id)

latest_issue = mgr.get(info.resource_id)
old_issue = mgr.get(info.resource_id, revision_id=info.revision_id)

print("latest issue:", latest_issue.data)
print("old issue:", old_issue.data)

revision_ids = mgr.list_revisions(info.resource_id)
for revision_id in revision_ids:
    rev = mgr.get_revision_info(info.resource_id, revision_id=revision_id)
    print("history:", rev.revision_id, rev.created_time, rev.created_by)
```

Run:

```bash
uvicorn main:app --reload
```