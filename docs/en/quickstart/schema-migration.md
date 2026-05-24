# Quickstart - Schema Migration

Schema evolves over time.

SpecStar helps you handle schema changes safely — without losing data.

⏱️ Estimated time: 5 minutes

---

## When do you need migration?

Schema changes can be divided into two categories:

- **Backward compatible changes** (no migration needed)
- **Breaking changes** (migration required)

---

## 1. Backward compatible changes

Some schema changes are automatically handled by SpecStar at runtime.

These include:

- adding new attributes with default values
- changing default values
- expanding Union / Literal types with new variants

### Example

Original schema:

```python
class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
```

Updated schema:

```python
class Issue(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
    priority: Literal["low", "medium", "high"] = "medium"
```

No migration is required.

When SpecStar reads older data, missing fields are automatically filled using default values.

---

## 2. Breaking changes

Breaking changes require explicit migration.

These include:

- adding new attributes **without default values**
- removing existing attributes
- narrowing Union / Literal types (removing variants)
- changing field types

> **Don't make a breaking change without bumping the schema version.** If you
> alter the struct incompatibly but keep the **same** version, existing rows can
> no longer be decoded. The list endpoints defensively **skip** such rows (one
> bad row won't fail the whole page), but `/{model}/count` still counts them —
> so `count` and the list disagree. By default SpecStar logs a warning
> (`… skipped N undecodable resource(s) that /count still counts …`). You can
> change this with `on_decode_error` (`skip` / `error` / `raw`) — see
> [API conventions](../howto/api-conventions.md#undecodable-stored-data-on_decode_error).
> The real fix is to give the new shape a new version and a migration step, as below.

---

## 3. Define versioned schemas

Keep the old schema and introduce a new version.

```python
class IssueV1(msgspec.Struct):
    title: str
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"


class Issue(msgspec.Struct):  # v2
    title: str
    priority: Literal["low", "medium", "high"]  # new required field
    description: str | None = None
    status: Literal["open", "in_progress", "resolved"] = "open"
```

---

## 4. Define migration logic

Write a function that converts old data into the new schema.

```python
def migrate_v1_to_v2(old: IssueV1) -> Issue:
    return Issue(
        title=old.title,
        priority="medium",  # default for existing data
        description=old.description,
        status=old.status,
    )
```

---

## 5. Register the migration

Attach the migration step when registering the new schema:

```python
from datetime import datetime
from specstar import spec, Schema

spec.configure(default_user="migration", default_now=datetime.utcnow)
spec.add_model(
    Schema(Issue, "v2").step(
        "v1",
        migrate_v1_to_v2,
        source_type=IssueV1,
    )
)
```

> Programmatic `resource_manager.migrate(...)` / `.switch(...)` calls require an
> **operation context** (current user + clock). Pass `default_user` /
> `default_now` to `configure()` as above, or wrap the call with
> `rm.using(user=..., now=...)`. Without it, write methods raise
> `MissingOperationContextError`.

This tells SpecStar how to upgrade data from `v1` → `v2`.

---

## 6. Execute migration

The migration endpoints are **not registered by default**. Opt in by adding
`MigrateRouteTemplate` before `add_model()`:

```python
from specstar import spec
from specstar.crud.route_templates.migrate import MigrateRouteTemplate

spec.add_route_template(MigrateRouteTemplate())
```

This mounts `POST /{model_name}/migrate/execute`,
`POST /{model_name}/migrate/test`, and
`POST /{model_name}/migrate/single/{resource_id}` (the path segment follows
`model_naming`; e.g. an `Issue` model is mounted under `/issue`).

Run migration via API:

```bash
curl -X POST http://127.0.0.1:8000/issue/migrate/execute \
  -H "Content-Type: application/json" \
  -d '{
    "limit": 10000
  }'
```

This will:

- scan existing resources
- convert old revisions using your migration function
- store them as new revisions in the latest schema

---

## 7. What happens after migration?

After migration:

- all new writes use the latest schema (`v2`)
- old data is preserved as historical revisions
- your system continues to support revision history seamlessly

---

## Why this matters

Schema changes are one of the hardest parts of maintaining a system.

With SpecStar:

- backward-compatible changes require no action
- breaking changes are explicit and controlled
- migration logic is versioned alongside your schema
- historical data is never lost

You evolve your schema without breaking your system.

---

## What’s next

If your application is evolving in place, backend setup becomes an important follow-up so migrations run against durable storage.

Next Steps:

- [Set up backend persistence and deployment choices](/specstar/guides/backend-setup)
- [Learn how revision history behaves in practice](/specstar/quickstart/data-versioning)
- [Move from demo to production](/specstar/guides/from-demo-to-production)