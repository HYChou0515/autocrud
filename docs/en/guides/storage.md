# Storage backends

AutoCRUD separates persistence into three related but distinct layers:

- **metadata** — IDs, revision information, search/index state, lifecycle flags
- **resource data** — the structured payload of the resource itself
- **blob data** — binary uploads and file-like artifacts

You choose the default backend with:

```python
crud.configure(storage_factory=...)
```

You can also override storage per model when one resource needs a different durability strategy.

---

## What the storage factory controls

| Factory | Metadata | Resource data | Blob data |
| --- | --- | --- | --- |
| `MemoryStorageFactory()` | memory | memory | memory |
| `DiskStorageFactory("./data")` | local files | local files | local files |
| `S3StorageFactory(...)` | SQLite synced to S3 | S3 | S3 |
| `PostgresStorageFactory(...)` | PostgreSQL | PostgreSQL | memory by default |
| `PostgreSQLS3StorageFactory(...)` | PostgreSQL | S3 | S3 |
| `PostgresDiskStorageFactory(...)` | PostgreSQL | local disk | memory by default |
| `PostgresDiskS3StorageFactory(...)` | PostgreSQL | local disk | S3 |

That last column matters.
If your app uses file uploads or binary fields, do not assume every SQL-backed setup automatically gives you durable blobs.

---

## Options

### DiskStorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import DiskStorageFactory

crud.configure(
    storage_factory=DiskStorageFactory("./data")
)
```

Best for:

- local development
- single-node deployments
- MVPs that need restart-safe persistence

Pros:

- zero extra infrastructure
- easy local inspection and backups
- blob persistence works out of the box

Cons:

- not ideal for multi-node deployments
- limited concurrent write scalability

---

### S3StorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import S3StorageFactory

crud.configure(
    storage_factory=S3StorageFactory(
        bucket="my-bucket",
        endpoint_url="https://s3.amazonaws.com",
    )
)
```

Best for:

- cloud deployments
- shared storage across app instances
- object-storage-first architectures

Pros:

- durable resource and blob storage
- works with AWS S3 and S3-compatible services such as MinIO
- no separate database required for the simplest cloud setup

Cons:

- metadata queries are less SQL-like than PostgreSQL-backed setups
- still requires object storage infrastructure and credentials

---

### PostgresStorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import PostgresStorageFactory

crud.configure(
    storage_factory=PostgresStorageFactory(
        connection_string="postgresql://user:pass@host:5432/appdb",
    )
)
```

Best for:

- production systems with query-heavy workloads
- teams that want a database-centric architecture
- APIs that mainly serve structured records rather than uploaded files

Pros:

- fast searchable metadata
- strong indexing and SQL operations
- all structured data stays in PostgreSQL

Cons:

- requires database infrastructure
- blob data is **not** durable by default, so binary-upload workloads need an additional plan

If you need durable file uploads as well, prefer `PostgresDiskS3StorageFactory` for the default production path, or use `PostgreSQLS3StorageFactory` when you want S3 for resource payloads too.

---

### PostgresDiskStorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import PostgresDiskStorageFactory

crud.configure(
    storage_factory=PostgresDiskStorageFactory(
        connection_string="postgresql://user:pass@host:5432/appdb",
        rootdir="./data",
    )
)
```

Best for:

- the recommended production setup
- systems that want PostgreSQL-backed metadata and search
- deployments that prefer keeping structured resource payloads on mounted disk

Pros:

- strong metadata querying in PostgreSQL
- straightforward local or mounted-volume resource persistence
- a good fit when blob uploads are handled separately in S3

Cons:

- blob durability is still a separate configuration decision
- not as stateless as storing resource payloads fully in object storage

Pair this setup with S3-backed blob handling when your application stores uploads or binary artifacts.

---

### PostgresDiskS3StorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import PostgresDiskS3StorageFactory

crud.configure(
    storage_factory=PostgresDiskS3StorageFactory(
        connection_string="postgresql://user:pass@host:5432/appdb",
        rootdir="./data",
        s3_bucket="my-blob-bucket",
    )
)
```

Best for:

- the default production-ready storage setup
- PostgreSQL-backed search and metadata
- disk-backed resource payloads plus durable S3 blob uploads

Pros:

- keeps structured payloads on local or mounted disk
- stores blobs durably in S3-compatible storage
- works out of the box with the current recommended architecture

Cons:

- still requires both database and object storage infrastructure
- resource payloads remain tied to mounted disk rather than full object storage

---

### PostgreSQLS3StorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import Encoding, PostgreSQLS3StorageFactory

crud.configure(
    storage_factory=PostgreSQLS3StorageFactory(
        connection_string="postgresql://user:pass@host:5432/appdb",
        s3_bucket="my-bucket",
        s3_region="us-east-1",
        encoding=Encoding.msgpack,
    )
)
```

Best for:

- production systems with durable uploads
- multi-node services
- teams that want PostgreSQL search plus object-storage durability

Pros:

- searchable metadata in PostgreSQL
- resource data and blobs stored durably in S3
- strong fit for production deployments

Cons:

- requires both database and object storage infrastructure
- more moving parts than local disk setups

---

### MemoryStorageFactory

```python
from autocrud import crud
from autocrud.resource_manager import MemoryStorageFactory

crud.configure(
    storage_factory=MemoryStorageFactory()
)
```

Best for:

- tests
- short-lived demos
- experiments where restart durability does not matter

⚠️ Data is lost when the process exits.

---

## Choosing a backend

| Use case | Recommended backend |
| --- | --- |
| unit tests and demos | `MemoryStorageFactory()` |
| local development or MVP | `DiskStorageFactory("./data")` |
| recommended production setup | `PostgresDiskS3StorageFactory(...)` |
| object-storage-first production | `PostgreSQLS3StorageFactory(...)` |
| cloud-first object storage setup | `S3StorageFactory(...)` |

Rule of thumb:

```text
start local → DiskStorageFactory
recommended production → PostgresDiskS3StorageFactory + RabbitMQ
prefer fully object-backed resource payloads → PostgreSQLS3StorageFactory
```
---

## Per-model override

Different resources can use different storage backends.

```python
from autocrud import AutoCRUD
from autocrud.resource_manager import DiskStorageFactory, S3StorageFactory

crud = AutoCRUD(
    storage_factory=DiskStorageFactory("./data")
)

crud.add_model(User)

crud.add_model(
    Image,
    storage=S3StorageFactory(bucket="image-bucket")
)
```

This is useful when:

- one resource is local-only while another needs cloud durability
- binary-heavy resources should live in object storage
- you want to migrate one model at a time rather than the whole system at once

All resources still share the same AutoCRUD programming model.

---

## Common gotchas

- call `crud.configure(...)` before `add_model(...)`
- do not use in-memory storage if restarts must preserve data
- if the app stores files, verify the selected factory gives you durable blob storage
- for jobs and workers, combine the storage decision with a queue decision from the [Job Queue quickstart](/autocrud/quickstart/job-queue)

