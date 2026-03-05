# References (Ref / RefType / OnDelete)

AutoCRUD uses `typing.Annotated` + metadata markers to express relationships between resources.

## The basic pattern

A reference field is typically a `str` holding another resource's **resource_id**:

```python
from typing import Annotated
from msgspec import Struct
from autocrud.types import Ref

class Monster(Struct):
    zone_id: Annotated[str, Ref("zone")]
```

Here `Ref("zone")` means:

* this field targets the resource named `"zone"`
* the stored value is a `resource_id` by default
* AutoCRUD may enforce referential integrity and build ref-related features

## OnDelete policies

Use `on_delete=` to define what happens when the referenced target is deleted:

* `OnDelete.dangling` (default): do nothing, the reference may become dangling
* `OnDelete.set_null`: set the referencing field to `null` (**requires Optional field**)
* `OnDelete.cascade`: delete the referencing resource as well

Example:

```python
from autocrud.types import Ref, OnDelete

class Monster(Struct):
    # set_null requires Optional / nullable type
    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None

    # cascade deletes the referencing resource
    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.cascade)]
```

## RefType: resource_id vs revision_id

### RefType.resource_id (default)

`RefType.resource_id` means the field stores a **resource_id**. These refs:

* participate in `on_delete` referential behavior
* can be auto-indexed for searchability
* can participate in "referrers" / relationship queries

### RefType.revision_id (version-aware refs)

`RefType.revision_id` means the field stores a version-aware reference:

* it may store a **revision_id** (pinned to a specific revision)
* or a **resource_id** meaning "latest"

These refs are intentionally treated differently:

* `on_delete` is always `dangling`
* they are not auto-indexed (by default behavior)
* they are excluded from referrers queries

Example:

```python
from autocrud.types import Ref, RefType

class Monster(Struct):
    zone_snapshot_id: Annotated[str, Ref("zone", ref_type=RefType.revision_id)]
```

## Deprecation: RefRevision

`RefRevision("zone")` is deprecated.
Use:

```python
Ref("zone", ref_type=RefType.revision_id)
```
