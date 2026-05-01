# Upgrading to 0.9

This page lists every breaking change introduced in 0.9 and shows the minimum
code edit required to migrate from 0.8.5.

---

## Quick checklist

- [ ] Replace removed `PostgreSQLStorageFactory` / `PostgreSQLDiskS3StorageFactory`
- [ ] Remove imports from deleted `specstar.permission.basic`
- [ ] Implement `save_many()` / `dump_all_revisions()` on any custom stores
- [ ] Update code that consumes the `dump()` generator
- [ ] Implement `load_records_bulk()` on any custom `IResourceManager` subclass
- [ ] Update callers that used the `None` return of `start_consume(block=False)`
- [ ] Run `backfill_revision_meta()` on every `ResourceManager` after deploying

---

## 1. Removed storage factory aliases

`PostgreSQLStorageFactory` and `PostgreSQLDiskS3StorageFactory` were deprecated in
0.8 with a runtime warning.  Both are now removed.

**Before**

```python
from specstar.resource_manager.storage_factory import (
    PostgreSQLStorageFactory,
    PostgreSQLDiskS3StorageFactory,
)
```

**After**

| Old name | Replacement |
| --- | --- |
| `PostgreSQLStorageFactory` | `PostgreSQLS3StorageFactory` (PostgreSQL meta + S3 revisions) or `PostgresStorageFactory` (PostgreSQL only) |
| `PostgreSQLDiskS3StorageFactory` | `PostgresDiskS3StorageFactory` |

```python
from specstar.resource_manager.storage_factory import (
    PostgreSQLS3StorageFactory,   # or PostgresStorageFactory
    PostgresDiskS3StorageFactory,
)
```

---

## 2. `specstar.permission.basic` removed

The module `specstar.permission.basic` and the class `IPermissionCheckerWithStore`
it contained have been deleted.  `StoreBackedPermissionChecker` now inherits
directly from `IPermissionChecker`.

**Before**

```python
from specstar.permission.basic import IPermissionCheckerWithStore

class MyChecker(IPermissionCheckerWithStore[MyResource]):
    ...
```

**After**

Use `StoreBackedPermissionChecker` (if you need the built-in `resource_manager`
property) or `IPermissionChecker` (if you manage the resource manager yourself).

```python
from specstar.permission.checker import IPermissionChecker
from specstar.permission.store_backed import StoreBackedPermissionChecker

# option A — use the built-in resource_manager integration
class MyChecker(StoreBackedPermissionChecker[MyResource]):
    ...

# option B — plain interface with no store coupling
class MyChecker(IPermissionChecker):
    ...
```

`DEFAULT_ROOT_USER` was also in `specstar.permission.basic`.  It is now exported
from `specstar.permission.checker`.

```python
# before
from specstar.permission.basic import DEFAULT_ROOT_USER

# after
from specstar.permission.checker import DEFAULT_ROOT_USER
```

---

## 3. Custom storage implementations must provide `save_many()` and `dump_all_revisions()`

In 0.8 the framework used `hasattr` to detect optional bulk methods and silently
fell back to item-by-item calls.  That fallback is removed in 0.9.

If you wrote a custom `IMetaStore`, add `save_many`:

```python
class MyMetaStore(IMetaStore):
    def save_many(self, metas: Iterable[ResourceMeta]) -> None:
        for meta in metas:
            self[meta.resource_id] = meta   # or a bulk insert
```

If you wrote a custom `IResourceStore`, add `dump_all_revisions` and `save_many`:

```python
class MyResourceStore(IResourceStore):
    def dump_all_revisions(
        self, resource_ids: Iterable[str]
    ) -> Iterable[tuple[RevisionInfo, bytes]]:
        for rid in resource_ids:
            for info, raw in self._iter_revisions(rid):
                yield info, raw

    def save_many(self, items: Iterable[tuple[RevisionInfo, bytes]]) -> None:
        for info, raw in items:
            self.save(info, io.BytesIO(raw))
```

---

## 4. `dump()` return type changed

`IResourceManager.dump()` (and `ResourceManager.dump()`) now yields typed record
objects instead of raw `(filename, IO[bytes])` tuples.

**Before**

```python
for name, stream in manager.dump():
    tar.addfile(tarinfo, stream)
```

**After**

```python
from specstar.resource_manager.dump_format import (
    MetaRecord, RevisionRecord, BlobRecord,
    HeaderRecord, ModelStartRecord, ModelEndRecord, EofRecord,
)

for record in manager.dump():
    if isinstance(record, MetaRecord):
        ...
    elif isinstance(record, RevisionRecord):
        ...
    elif isinstance(record, BlobRecord):
        ...
```

The backup/restore routes (`BackupRouteTemplate` / `RestoreRouteTemplate`) handle
this internally — no changes needed there.

---

## 5. `load_records_bulk()` is now a required abstract method

If you subclass `IResourceManager` directly, add:

```python
from specstar.crud.core import LoadStats
from specstar.resource_manager.dump_format import MetaRecord, RevisionRecord, BlobRecord
from specstar.types import OnDuplicate

class MyResourceManager(IResourceManager[T]):
    def load_records_bulk(
        self,
        meta_records: list[MetaRecord],
        revision_records: list[RevisionRecord],
        blob_records: list[BlobRecord],
        on_duplicate: OnDuplicate = OnDuplicate.raise_error,
    ) -> LoadStats:
        stats = LoadStats()
        for r in meta_records + revision_records + blob_records:
            loaded = self.load_record(r, on_duplicate=on_duplicate)
            if loaded:
                stats.loaded += 1
        return stats
```

`ResourceManager` (the concrete class) already implements this — only custom
subclasses of the abstract base are affected.

---

## 6. `start_consume(block=False)` now returns a thread

When `block=False`, `start_consume()` previously returned `None`.  It now returns
the `threading.Thread` that was started (or `None` if no queue backend is
configured).

```python
# before — return value was always None
manager.start_consume(block=False)

# after — save the thread if you want to join later
thread = manager.start_consume(block=False)
if thread is not None:
    thread.join(timeout=30)
```

Calls with `block=True` (the default) are unaffected.

---

## 7. `ResourceMeta` rev fields and backfill

Five new fields are embedded in `ResourceMeta` to avoid N+1 reads when filtering
resources by their current revision:

| Field | Type | Description |
| --- | --- | --- |
| `rev_status` | `RevisionStatus \| UnsetType` | Status of the current revision |
| `rev_created_by` | `str \| UnsetType` | User who created the current revision |
| `rev_updated_by` | `str \| UnsetType` | User who last updated the current revision |
| `rev_created_time` | `datetime \| UnsetType` | Creation time of the current revision |
| `rev_updated_time` | `datetime \| UnsetType` | Last-update time of the current revision |

All fields default to `UNSET`.  Resources created after upgrading are populated
automatically.  Resources created before upgrading will have `UNSET` until you run:

```python
count = manager.backfill_revision_meta()
print(f"backfilled {count} resources")
```

Run this once after deploying — either at startup or as a one-off script.

!!! warning "Queries using `rev_*` filters will not match un-backfilled resources"
    `is_match_query` treats `UNSET` as no-match for any `rev_*` filter, so
    resources that have not been backfilled will be silently excluded.

### Database schema

For SQLite, PostgreSQL, and SQLAlchemy meta stores the new columns are added
automatically on first connection (via `ALTER TABLE ADD COLUMN IF NOT EXISTS`).
No manual migration is needed.

If you use a custom meta store, add these columns to your table:

```sql
ALTER TABLE resource_meta ADD COLUMN rev_status      TEXT;
ALTER TABLE resource_meta ADD COLUMN rev_created_by  TEXT;
ALTER TABLE resource_meta ADD COLUMN rev_updated_by  TEXT;
ALTER TABLE resource_meta ADD COLUMN rev_created_time REAL;   -- UNIX timestamp
ALTER TABLE resource_meta ADD COLUMN rev_updated_time REAL;
```

---

## New features in 0.9

These additions are backwards-compatible and require no migration.

### Query Builder `rev_*` helpers

Filter and sort resources by current-revision attributes without any extra reads:

```python
from specstar.query import QB
from datetime import datetime

# resources whose current revision is draft
QB.rev_status().eq("draft")

# resources last updated by alice
QB.rev_updated_by().eq("alice")

# resources whose current revision was created this week
QB.rev_created_time().this_week()
```

The corresponding `ResourceMetaSearchQuery` fields (`rev_statuses`,
`rev_created_bys`, `rev_updated_bys`, `rev_created_time_start/end`,
`rev_updated_time_start/end`) and HTTP query parameters are also available.

### `ResourceMetaSortKey` additions

```python
from specstar.query_types import ResourceMetaSortKey

# sort by current-revision creation time
ResourceMetaSortKey.rev_created_time
ResourceMetaSortKey.rev_updated_time
```

### `IStorageFactory.build_blob_store()` hook

Factories that own an object backend can now expose it directly:

```python
class MyFactory(IStorageFactory):
    def build_blob_store(self) -> IBlobStore | None:
        return MyS3BlobStore(self._bucket)
```

The default returns `None` — no existing factory is affected.
