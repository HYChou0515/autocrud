# ResourceManager — Complete API Reference

The `ResourceManager` is the core interface for all programmatic CRUD operations. Every model registered with `crud.add_model()` gets its own ResourceManager instance.

## Obtaining a ResourceManager

```python
rm = crud.get_resource_manager(User)     # by type
rm = crud.get_resource_manager("user")   # by resource name
```

## Operation Context

Write operations require a user and timestamp for audit trails. Three approaches:

```python
import datetime as dt

# 1. Context manager (recommended for batch operations)
with rm.using(user="admin", now=dt.datetime.now()):
    rm.create(data1)
    rm.create(data2)
    rm.update(id, data3)

# 2. Per-call parameters
rm.create(data, user="admin", now=dt.datetime.now())

# 3. Global defaults (set in crud.configure)
crud.configure(default_user="system", default_now=lambda: dt.datetime.now())
```

> **Note**: `meta_provide()` is deprecated — use `using()` instead.

## Complete Method Reference

### Create Operations

```python
# Create a new resource → returns RevisionInfo
info = rm.create(
    data: T,                        # Struct, Pydantic BaseModel, or dict
    *,
    status: RevisionStatus = UNSET, # override default_status (draft | stable)
    user: str = UNSET,
    now: dt.datetime = UNSET,
    resource_id: str = UNSET,       # custom resource_id (auto-generated if omitted)
)
print(info.resource_id)             # "550e8400-..."
print(info.revision_id)            # "550e8400-...:1"

# Upsert: create if new, update if exists
info = rm.create_or_update(resource_id, data)
```

### Read Operations

```python
# Get current revision
resource = rm.get(resource_id)
print(resource.data)               # User(name="Alice", ...)
print(resource.info)               # RevisionInfo(revision_id=..., status=...)
print(resource.info.revision_id)   # "abc-123:3"

# Get specific revision
resource = rm.get(resource_id, revision_id="abc-123:1")

# Get specific revision directly
resource = rm.get_resource_revision(resource_id, revision_id)

# Get only metadata (no data fetch)
meta = rm.get_meta(resource_id)
print(meta.current_revision_id, meta.is_deleted, meta.total_revision_count)

# Get revision-level metadata
info = rm.get_revision_info(resource_id)
info = rm.get_revision_info(resource_id, revision_id="abc-123:1")

# List all revision IDs for a resource
revisions = rm.list_revisions(resource_id)  # ["abc-123:1", "abc-123:2", ...]

# Check existence
if rm.exists(resource_id):
    ...
if rm.revision_exists(resource_id, revision_id):
    ...

# Partial field fetch (only retrieve specific fields)
partial = rm.get_partial(resource_id, revision_id, ["name", "email"])
```

### Update Operations

```python
# Update — creates a NEW revision (immutable history)
info = rm.update(
    resource_id: str,
    data: T,
    *,
    status: RevisionStatus = UNSET,
    user: str = UNSET,
    now: dt.datetime = UNSET,
)
# After: revision_id = "abc-123:4" (new), parent = "abc-123:3"

# Modify — edits CURRENT revision in-place (for draft workflows)
info = rm.modify(
    resource_id: str,
    data: T | JsonPatch | UnsetType = UNSET,
    status: RevisionStatus = UNSET,
    *,
    user: str = UNSET,
    now: dt.datetime = UNSET,
)
# After: same revision_id, updated_time changed

# Patch — RFC 6902 JSON Patch operations
info = rm.patch(resource_id, [
    {"op": "replace", "path": "/name", "value": "New Name"},
    {"op": "add", "path": "/tags/-", "value": "new-tag"},
])
```

### Delete & Restore Operations

```python
# Soft delete — sets is_deleted=True, no revision change
meta = rm.delete(resource_id)

# Restore — reverses soft delete
meta = rm.restore(resource_id)

# Hard delete — removes resource + ALL revisions permanently
meta = rm.permanently_delete(resource_id)
```

### Revision Management

```python
# Switch active revision (like git checkout)
# r1 → r2 → r3(HEAD) → switch to r1 → r1(HEAD)
meta = rm.switch(resource_id, revision_id="abc-123:1")

# Migrate revision to latest schema
meta = rm.migrate(resource_id)                          # current revision
meta = rm.migrate(resource_id, revision_id="abc-123:1") # specific old revision

# Switch to unmigrated revision requires migration first
from autocrud import RevisionNotMigratedError
try:
    rm.switch(resource_id, old_revision_id)
except RevisionNotMigratedError:
    rm.migrate(resource_id, revision_id=old_revision_id)
    rm.switch(resource_id, old_revision_id)
```

### Search & Query

```python
from autocrud.query import QB

# Search → list of ResourceMeta (metadata only, fast)
metas = rm.search_resources(
    QB["level"].gte(50).sort("-level").limit(10)
)
for meta in metas:
    print(meta.resource_id, meta.indexed_data)

# List → list of SearchedResource (includes data + meta + info)
results = rm.list_resources(
    QB["level"].gte(50).sort("-level").limit(10),
    returns=["data", "meta", "revision_info"],  # what to include
    partial=["name", "level"],                   # partial fields only
)
for sr in results:
    print(sr.data.name, sr.meta.created_time, sr.info.revision_id)

# Count matching resources
count = rm.count_resources(QB["level"].gte(50))
```

### Blob Operations

```python
from autocrud.types import Binary

# Blobs are auto-stored when creating/updating resources with Binary fields
rm.create(Image(file=Binary(data=b"...", content_type="image/png")))

# Retrieve blob by file_id
blob = rm.get_blob(file_id)    # Binary(data=..., content_type=..., size=...)

# Get presigned URL (S3 backends)
url = rm.get_blob_url(file_id)

# Stream download
stream = rm.get_blob_stream(file_id)

# Direct blob response (for HTTP endpoints)
response = rm.get_blob_response(file_id)
```

### Export

```python
# Export resources as generator of records
for record in rm.dump(query=None):  # None = all resources
    # record is MetaRecord, RevisionRecord, or BlobRecord
    ...
```

### Message Queue

```python
# Start consuming jobs (for Job[T] models)
rm.start_consume(
    block=False,                   # False = background thread
    custom_creation="all",         # also consume async create actions
    custom_update="all",           # also consume async update actions
)
# custom_creation/custom_update can also be list of specific job names
```

## Return Types

| Method | Returns | Key Fields |
|--------|---------|------------|
| `create`, `update`, `modify`, `patch` | `RevisionInfo` | `.resource_id`, `.revision_id`, `.parent_revision_id`, `.status`, `.schema_version`, `.created_time`, `.data_hash` |
| `delete`, `restore`, `switch`, `migrate`, `permanently_delete` | `ResourceMeta` | `.resource_id`, `.current_revision_id`, `.is_deleted`, `.total_revision_count`, `.created_time`, `.updated_time`, `.indexed_data` |
| `get`, `get_resource_revision` | `Resource[T]` | `.data` (T), `.info` (RevisionInfo) |
| `search_resources` | `list[ResourceMeta]` | metadata list |
| `list_resources` | `list[SearchedResource[T]]` | `.data`, `.info`, `.meta` (all optional based on `returns`) |
| `count_resources` | `int` | count |
| `get_meta` | `ResourceMeta` | metadata |
| `get_revision_info` | `RevisionInfo` | revision metadata |
| `list_revisions` | `list[str]` | revision ID strings |
| `exists` | `bool` | existence check |

## Properties

```python
rm.resource_type          # type — the Struct class
rm.resource_name          # str — registered name (e.g., "user")
rm.schema_version         # str — current schema version
rm.pydantic_type          # type | None — original Pydantic class if used
rm.indexed_fields         # list — indexed field definitions
rm.user                   # str — current context user
rm.now                    # dt.datetime — current context timestamp
```
