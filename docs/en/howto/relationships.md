# Relationships & referential actions

This page explains how SpecStar uses `Ref(...)` metadata to:
- validate relationship declarations
- install referential integrity behaviors (`on_delete`)
- support relationship discovery (ref routes / referrers)
- auto-index reference fields (resource_id refs)

## Declare a relationship

```python
from typing import Annotated
from msgspec import Struct
from specstar.types import Ref, OnDelete, RefType

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

### `on_delete` defaults to `dangling` — i.e. **no** referential protection

If you omit `on_delete`, a `Ref` uses `OnDelete.dangling`: deleting a referenced
resource **succeeds** and leaves the referencing field pointing at a now-missing
resource. Choose explicitly when you need integrity:

- `OnDelete.restrict` — refuse to delete while referenced (raises, HTTP 409)
- `OnDelete.cascade` — delete the referencing resource too
- `OnDelete.set_null` — null the referencing field (Optional only)

Also note references are **not** validated on write by default — see
`validate_refs` if you want write-time existence checks.

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

If `ref_type != RefType.resource_id`, SpecStar requires:

* `on_delete = OnDelete.dangling`

So this is invalid:

```python
Ref("zone", ref_type=RefType.revision_id, on_delete=OnDelete.cascade)  # invalid
```

## What happens at runtime

### When you call `apply(router)`

SpecStar:

* collects ref metadata while registering models
* validates that ref targets exist (warns if dangling targets)
* installs referential integrity event handlers
* may add ref-related routes (referrers + relationship endpoints)

### When the referenced resource is deleted

Behavior depends on `on_delete`:

* `dangling` *(default)*: no action, ref stays as-is — referencing rows
  end up pointing at a deleted target.
* `set_null`: referencing field set to null (for nullable fields only).
* `cascade`: referencing resources are deleted too.
* `restrict`: **refuse the delete** while any other resource still
  references this one. The `delete` call raises
  `ResourceConflictError` (HTTP 409 on routes) with a message naming the
  blocking source rows. Use this when you want callers to clean up
  references explicitly rather than auto-cascading or letting refs go
  dangling.

```python
class Zone(msgspec.Struct):
    name: str

class Monster(msgspec.Struct):
    name: str
    zone_id: Annotated[str, Ref("zone", on_delete=OnDelete.restrict)]
```

```
DELETE /zone/{zid}     # 200 when no monsters reference the zone
                       # 409 when one or more do — body names the blockers
DELETE /monster/{mid}  # remove the referencer
DELETE /zone/{zid}     # now 200
```

(Exact semantics may depend on your storage and event handler implementation.)

## Auto-indexing behavior

For `RefType.resource_id`:

* SpecStar may auto-index ref fields to make relationship queries and filtering efficient.

For `RefType.revision_id`:

* Auto-indexing is intentionally disabled by default because values may be revision_id or resource_id.

## Write-time validation (opt-in)

By default, you can create or update a resource whose `Ref(...)` field
points at a *non-existent* target — the reference becomes dangling
immediately. SpecStar leaves this open by default because in a versioned
system, the validation policy varies (e.g. should a soft-deleted target
count? what about cross-system refs?).

To force ref targets to exist at write time, opt in:

```python
spec = SpecStar(validate_refs=True)
# or
spec.configure(validate_refs=True)
```

With it on, `POST` / `PUT` / `PATCH` / `modify()` calls reject the
write with `422` (or `ValidationError` programmatically) when any
`RefType.resource_id` field value does not resolve to an existing,
non-deleted resource. `RefType.revision_id` refs are not validated —
those legitimately accept either revision ids or bare resource ids.

```
POST /monster  {"name": "B", "zone_id": "zone:never-existed"}
# → 422 "Reference target(s) not found: zone_id='zone:never-existed'"
```

## Recommended practices

* Use `RefType.resource_id` for true relational links between resources.
* Use `RefType.revision_id` only when you need a stable snapshot pointer.
* Prefer `set_null` for optional relationships and `cascade` only when ownership is strict.
