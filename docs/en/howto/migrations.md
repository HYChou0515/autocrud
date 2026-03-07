# Migrations with Schema

`Schema[T]` is the unified descriptor for:
- **target schema version**
- optional **validator**
- **migration graph** (chain + parallel paths)
- optional **encoding** for intermediate steps

## Mental model

A Schema defines a directed graph of version transitions:

- `.step(from_ver, fn)` appends a step to the **current chain**
- `.plus(from_ver, fn)` starts a **new chain** (parallel path)
- at runtime, AutoCRUD / ResourceManager uses **BFS shortest path** from stored version → target version

## Reindex-only (version bump)

If you bump version with no steps:

```python
Schema(User, "v2")
```

This means: “target version changes; no transforms are applied”.

## Single-step migration

```python
def v1_to_v2(bio):
    # bio: IO[bytes] of stored payload
    ...
    return migrated_obj

schema = Schema(User, "v2").step("v1", v1_to_v2)
```

## Typed migration (recommended)

Instead of manually reading and decoding bytes, use `source_type` to let the framework handle it:

```python
def v1_to_v2(data: UserV1) -> UserV2:
    return UserV2(name=data.name, age=data.age, role="user")

schema = Schema(UserV2, "v2").step("v1", v1_to_v2, source_type=UserV1)
```

Benefits:

* No boilerplate `data.read()` + `msgspec.json.decode(...)` in every function
* In multi-step chains, objects are passed directly between typed steps (no intermediate serialization)
* Works with both `msgspec.Struct` and Pydantic `BaseModel` as `source_type`

Multi-step typed chain:

```python
schema = (
    Schema(UserV3, "v3")
    .step("v1", v1_to_v2, source_type=UserV1)
    .step("v2", v2_to_v3, source_type=UserV2)
)
```

You can also mix typed and legacy steps in the same chain.

## Chain migration (auto-infer `to`)

```python
schema = (
    Schema(User, "v3")
    .step("v1", v1_to_v2)  # inferred to "v2" from next step's from_ver
    .step("v2", v2_to_v3)  # inferred to "v3" from Schema target version
)
```

Rules:

* If a step is not the last step in a chain, its `to` is inferred from the next step’s `from_ver`.
* If the next step uses regex `from_ver`, inference is impossible → you must set `to=` explicitly.

## Parallel paths with `.plus()`

```python
schema = (
    Schema(User, "v3")
    .step("v1", v1_to_v2)
    .step("v2", v2_to_v3)
    .plus("v1", v1_to_v3_shortcut)  # new chain: v1 -> v3
)
```

At runtime, BFS chooses the shortest path:

* `v1 -> v3` beats `v1 -> v2 -> v3` if both exist.

## Regex `from_ver`

You can use `re.compile(...)` for `from_ver` to match versions that are not known at authoring time:

```python
import re

schema = Schema(User, "v3").step(re.compile(r"v1-.*"), v1_family_to_v3, to="v3")
```

Notes:

* regex edges are expanded at runtime based on versions observed from persistence
* always set `to=` when regex is involved (to avoid inference errors)

## Encoding for intermediate steps

Multi-step migrations re-encode intermediate objects back into bytes for the next step.
`ResourceManager` will call `schema.set_encoding(...)` so intermediate encoding matches storage.

If you need to do it manually:

```python
schema.set_encoding("msgpack")  # or "json"
```

## Validation

Attach a validator once and reuse it on every write:

```python
schema = Schema(User, "v2", validator=my_validator).step("v1", v1_to_v2)
```

Validator types follow AutoCRUD conventions (callable / IValidator / Pydantic model).

## Legacy IMigration adapter

If you still have old `IMigration` implementations:

```python
schema = Schema.from_legacy(old_migration)
```

This wraps the migration and preserves `schema_version` + `migrate()` compatibility.

## Migrating specific revisions

By default, `migrate()` migrates only the **current revision** of a resource.
Older revisions remain at their original `schema_version` until explicitly migrated.

This matters when you want to **switch** back to an older revision — AutoCRUD
will raise `RevisionNotMigratedError` if that revision has not been migrated yet.

```python
from autocrud import RevisionNotMigratedError

# After a schema upgrade, migrate the current revision
resource_manager.migrate(resource_id)

# Attempting to switch to an older, unmigrated revision
try:
    resource_manager.switch(resource_id, old_revision_id)
except RevisionNotMigratedError:
    # Migrate the specific revision first
    resource_manager.migrate(resource_id, revision_id=old_revision_id)
    # Now switch succeeds
    resource_manager.switch(resource_id, old_revision_id)
```

Notes:

* Migrating a specific revision **does not** update `meta.schema_version` — only the revision's own `schema_version` changes.
* The `migrate/single/{resource_id}` HTTP endpoint also accepts an optional `revision_id` query parameter.
