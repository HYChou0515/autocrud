# Constraints (Unique)

AutoCRUD supports a built-in uniqueness constraint via `Unique()` metadata.

## Declare unique fields

Use `typing.Annotated`:

```python
from typing import Annotated
from msgspec import Struct
from autocrud.types import Unique

class User(Struct):
    username: Annotated[str, Unique()]
    email: Annotated[str, Unique()]
    age: int = 0
```

## What Unique means (precise semantics)

A field marked with `Unique()` must be unique among **non-deleted** resources
of the same resource type.

* **Soft-deleted resources are ignored** when checking uniqueness.
* **`None` values are ignored** (i.e. `None` can repeat without violating uniqueness).

If a duplicate is detected, AutoCRUD raises `UniqueConstraintError`.

## When does the check run?

Uniqueness is checked on write operations where unique-relevant data changes,
such as:

* create
* update / modify / patch (when the unique fields actually change)

## How it works (implementation notes)

AutoCRUD uses a `UniqueConstraintChecker`:

* detects unique fields from `Unique()` annotations (or accepts an explicit list)
* ensures each unique field is present in `ResourceManager` indexed fields (auto-adds if missing)
* queries storage for `is_deleted=False` and `field == value` to find conflicts

## Update behavior (exclude current resource)

When updating a resource, AutoCRUD excludes the current resource ID so that:

* updating a resource without changing the unique value does **not** fail
* changing to a value owned by another resource fails

## Debugging uniqueness failures

If you see `UniqueConstraintError`:

* find the conflicting resource ID reported in the error
* verify that the conflicting resource is not deleted
* verify the field value being written is not `None`
* verify your storage backend supports searching indexed fields correctly
