# Relationships & referential actions

This page explains how AutoCRUD uses `Ref(...)` metadata to:
- validate relationship declarations
- install referential integrity behaviors (`on_delete`)
- support relationship discovery (ref routes / referrers)
- auto-index reference fields (resource_id refs)

## Declare a relationship

```python
from typing import Annotated
from msgspec import Struct
from autocrud.types import Ref, OnDelete, RefType

class Zone(Struct):
    name: str

class Guild(Struct):
    name: str

class Monster(Struct):
    zone_id: Annotated[str, Ref("zone")]  # resource_id ref

    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None

    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.cascade)]

    # version-aware ref (pinned or latest)
    zone_snapshot_id: Annotated[str, Ref("zone", ref_type=RefType.revision_id)]
```

## Important constraints (common pitfalls)

### `OnDelete.set_null` requires Optional

If you use `on_delete=OnDelete.set_null`, the field must be nullable:

✅ good:

```python
guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None
```

❌ bad (will raise ValueError during model registration):

```python
guild_id: Annotated[str, Ref("guild", on_delete=OnDelete.set_null)]
```

### revision refs must be dangling

If `ref_type != RefType.resource_id`, AutoCRUD requires:

* `on_delete = OnDelete.dangling`

So this is invalid:

```python
Ref("zone", ref_type=RefType.revision_id, on_delete=OnDelete.cascade)  # invalid
```

## What happens at runtime

### When you call `apply(router)`

AutoCRUD:

* collects ref metadata while registering models
* validates that ref targets exist (warns if dangling targets)
* installs referential integrity event handlers
* may add ref-related routes (referrers + relationship endpoints)

### When the referenced resource is deleted

Behavior depends on `on_delete`:

* `dangling`: no action, ref stays as-is
* `set_null`: referencing field set to null (for nullable fields only)
* `cascade`: referencing resources are deleted too

(Exact semantics may depend on your storage and event handler implementation.)

## Auto-indexing behavior

For `RefType.resource_id`:

* AutoCRUD may auto-index ref fields to make relationship queries and filtering efficient.

For `RefType.revision_id`:

* Auto-indexing is intentionally disabled by default because values may be revision_id or resource_id.

## Recommended practices

* Use `RefType.resource_id` for true relational links between resources.
* Use `RefType.revision_id` only when you need a stable snapshot pointer.
* Prefer `set_null` for optional relationships and `cascade` only when ownership is strict.
