# Storage backends

AutoCRUD separates **metadata** and **resource data** storage via `IStorage` / `IStorageFactory`.

A storage factory is configured at `AutoCRUD(...)` construction time or via:

```python
crud.configure(storage_factory=...)
```

Per model, you can also pass an explicit storage backend to `add_model()`.

This allows different resources to use different storage systems.

---

## Options

### DiskStorageFactory (minimal viable production)

Stores everything locally.

| Component | Backend          |
| --------- | ---------------- |
| meta      | SQLite file      |
| revision  | filesystem files |
| blob      | filesystem       |

Example:

```python
from autocrud import AutoCRUD
from autocrud.storage.disk import DiskStorageFactory

crud = AutoCRUD(
    storage_factory=DiskStorageFactory("./data")
)
```

Best for:

* local development
* single-node deployments
* small to medium systems

Pros:

* zero infrastructure
* simple backups
* easy debugging

Cons:

* not horizontally scalable
* limited concurrent writers

---

### S3StorageFactory

Stores revisions and blobs in object storage (S3 compatible).

| Component | Backend             |
| --------- | ------------------- |
| meta      | SQLite stored in S3 |
| revision  | S3 objects          |
| blob      | S3                  |

Example:

```python
from autocrud.storage.s3 import S3StorageFactory

crud = AutoCRUD(
    storage_factory=S3StorageFactory(
        bucket="my-bucket",
        endpoint_url="https://s3.amazonaws.com"
    )
)
```

Best for:

* cloud deployments
* large datasets
* multi-node services

Pros:

* highly scalable
* cheap storage
* cloud-native

Cons:

* metadata queries slower than SQL
* requires object storage infrastructure

---

### PostgresStorageFactory

Stores metadata in PostgreSQL while keeping large data in S3.

| Component | Backend          |
| --------- | ---------------- |
| meta      | PostgreSQL table |
| revision  | S3 objects       |
| blob      | S3               |

Example:

```python
from autocrud.storage.postgres import PostgresStorageFactory

crud = AutoCRUD(
    storage_factory=PostgresStorageFactory(
        postgres_url="postgresql://user:pass@host/db",
        bucket="my-bucket"
    )
)
```

Best for:

* production systems
* heavy query workloads
* large datasets with indexing

Pros:

* fast queries
* scalable storage
* powerful indexing

Cons:

* requires database infrastructure
* slightly more complex setup

---

### MemoryStorageFactory

Stores everything in memory.

| Component | Backend        |
| --------- | -------------- |
| meta      | in-memory dict |
| revision  | in-memory dict |
| blob      | memory         |

Example:

```python
from autocrud.storage.memory import MemoryStorageFactory

crud = AutoCRUD(
    storage_factory=MemoryStorageFactory()
)
```

Best for:

* testing
* unit tests
* demos

⚠️ Data is lost when the process exits.

---

## Choosing a backend

| Use case               | Recommended backend      |
| ---------------------- | ------------------------ |
| unit tests             | `MemoryStorageFactory`   |
| local development      | `DiskStorageFactory`     |
| simple production      | `DiskStorageFactory`     |
| cloud storage          | `S3StorageFactory`       |
| large-scale production | `PostgresStorageFactory` |

Rule of thumb:

```
small project → Disk
cloud system → S3
large system → Postgres + S3
```

---

## Per-model override

Different resources can use different storage backends.

Example:

```python
crud = AutoCRUD(
    storage_factory=DiskStorageFactory("./data")
)

crud.add_model(User)

crud.add_model(
    Image,
    storage=S3StorageFactory(bucket="image-bucket")
)
```

This allows:

* hot data in Postgres
* large data in S3
* local data on disk

All resources still share the same `ResourceManager` API.
