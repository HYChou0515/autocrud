# Data model

AutoCRUD is built around a single idea:

**`ResourceManager` is the only place you manipulate resources.**

You should not write SQL, touch S3, or talk to blob storage directly. Everything goes through `ResourceManager`, which coordinates:

- **`IStorage`**: metadata + revision data
- **Blob store**: binary payload offloading (optional, but usually enabled)

Conceptually:

```

ResourceManager
├── IStorage
│     ├── meta store   (ResourceMeta)
│     └── revision store (RevisionInfo + data bytes per revision)
└── blob store (Binary payload)

```

## Resource

At the API layer, a resource is returned as:

```python
class Resource(msgspec.Struct, Generic[T]):
    info: RevisionInfo
    data: T
```

* `data` is your domain object (`msgspec.Struct` recommended)
* `info` is **revision-level metadata** for the returned revision

Resource-level metadata (`ResourceMeta`) is accessed via dedicated endpoints (or included in list/get responses via `returns=meta`).

## IDs

### `resource_id`

* A UUID string
* Created at `create()` time

### `revision_id`

AutoCRUD uses a human-readable revision identifier:

* `revision_id = "{resource_id}:{n}"`

Example:

* `f1b2...:1`
* `f1b2...:2`

## Revision graph and branching

Revisions behave like Git commits:

* `update()` always creates a new revision (a new node)
* `switch()` moves the resource "HEAD" pointer to an existing revision
* updating after a switch can create branches

Example:

```
r1 -> r2 -> r3 (HEAD)
```

After switching to `r2`:

```
r1 -> r2 (HEAD) -> r3
```

After updating from `r2`:

```
r1 -> r2 -> r4 (HEAD)
          \
           -> r3
```

So AutoCRUD maintains **a revision DAG**, not just a linear history.

## Revision status: `draft` vs `stable`

AutoCRUD uses `RevisionStatus` to support draft workflows:

* `draft`: editable in-place (via `modify()`), no restrictions
* `stable`: immutable data by default (data cannot be modified in-place)

Rules:

* `stable` **cannot** `modify(data)`
  but it **can** be converted to `draft` (using `modify(status=draft)`), and then edited.
* `draft` has no restrictions: it can be `update()` (new revision) and can be `modify()` (in-place)

This gives you a clean workflow:

* Use `update()` when you want a new revision in history
* Use `modify()` when you want to mutate a draft without growing history

## ResourceMeta vs RevisionInfo

AutoCRUD stores two levels of metadata:

### Resource-level meta: `ResourceMeta`

`ResourceMeta` describes the resource as a whole:

* `resource_id`
* `current_revision_id` (HEAD pointer)
* `schema_version` (current schema version for this resource)
* `total_revision_count`
* audit fields (`created_*`, `updated_*`)
* `is_deleted`
* `indexed_data` (for search)

### Revision-level meta: `RevisionInfo`

`RevisionInfo` describes a specific revision:

* `revision_id`
* `parent_revision_id`
* `schema_version` and `parent_schema_version`
* `status` (`draft`/`stable`)
* audit fields (`created_*`, `updated_*`)
* optional `data_hash`

Important: `updated_time` may differ from `created_time` **only** when a revision is modified in place (draft `modify()`).

## Timestamp semantics

### `update()` (new revision)

* `ResourceMeta.created_time`: unchanged
* `RevisionInfo.created_time`: new
* `RevisionInfo.updated_time`: equals created_time (new revision)
* `ResourceMeta.updated_time`: equals the new revision’s created/updated time

### `modify()` (in-place revision)

* `revision_id`: unchanged
* `parent_revision_id`: unchanged
* `RevisionInfo.created_time`: unchanged
* `RevisionInfo.updated_time`: updated
* `ResourceMeta.created_time`: unchanged
* `ResourceMeta.updated_time`: updated (matches `RevisionInfo.updated_time`)

## Soft delete / restore

### `delete()`

AutoCRUD uses soft delete:

* Only flips `ResourceMeta.is_deleted = True`
* Does **not** create a new revision
* Revision history is preserved
* Updates `ResourceMeta.updated_time` / `updated_by`

### `restore()`

* Sets `ResourceMeta.is_deleted = False` if it was deleted
* Does not create a new revision

## Binary payloads (blob store)

AutoCRUD supports efficient binary storage via `Binary` fields:

* On `create()` / `update()` / `modify()`, `ResourceManager` scans the data object
* Any `Binary(data=...)` is:

  1. extracted
  2. stored in the blob store
  3. replaced in the stored resource data with a reference (`file_id`, `size`, `content_type`)
  4. `data` is cleared (not persisted in the resource payload)

This keeps resource payloads small and makes blobs independently addressable.

## Migration is a ResourceManager concern

Migration happens at the `ResourceManager` layer (not in storage):

* Stored bytes are migrated to the latest schema version when you run `migrate()`
* Resource schema version is tracked on:

  * `ResourceMeta.schema_version`
  * `RevisionInfo.schema_version`
* Migration updates `indexed_data` based on migrated data

If a user requests an old revision, AutoCRUD attempts to decode it using the current schema.
If decoding fails, the revision is ignored (not returned as 404). Use migration APIs to fix it.
