# Storage Backends & Message Queue — Detailed Reference

## Storage Architecture

AutoCRUD splits persistence into three layers:

| Layer | Interface | Purpose |
|-------|-----------|---------|
| **MetaStore** | `IMetaStore` | Resource metadata, search indexing |
| **ResourceStore** | `IResourceStore` | Revision data (serialized payloads) |
| **BlobStore** | `IBlobStore` | Binary files (content-hash addressed) |

A `StorageFactory` creates all three for each registered model.

## Storage Factory Options

### MemoryStorageFactory

In-memory storage. Data lost on process exit. Best for testing and demos.

```python
from autocrud.resource_manager.storage_factory import MemoryStorageFactory

crud.configure(storage_factory=MemoryStorageFactory())
```

| Component | Backend |
|-----------|---------|
| Meta | in-memory dict |
| Revision | in-memory dict |
| Blob | in-memory |

### DiskStorageFactory

Local filesystem. SQLite for metadata, files for revisions. Zero infrastructure.

```python
from autocrud.resource_manager.storage_factory import DiskStorageFactory

crud.configure(storage_factory=DiskStorageFactory(rootdir="./data"))
```

| Component | Backend |
|-----------|---------|
| Meta | SQLite file |
| Revision | filesystem files |
| Blob | filesystem |

**Best for**: local development, single-node deployments, small-medium systems.

### S3StorageFactory

Cloud object storage. SQLite DB synced to S3 for metadata, S3 for data.

```python
from autocrud.resource_manager.storage_factory import S3StorageFactory

crud.configure(storage_factory=S3StorageFactory(
    bucket="my-bucket",
    access_key_id="...",                 # default: "minioadmin" (MinIO)
    secret_access_key="...",             # default: "minioadmin" (MinIO)
    region_name="us-east-1",
    endpoint_url="http://localhost:9000", # MinIO; omit for AWS S3
    prefix="app-data/",                  # S3 key prefix
    encoding="json",                     # json or msgpack
    auto_sync=True,                      # auto-sync SQLite to S3
    sync_interval=0,                     # 0 = immediate, N = seconds
    enable_locking=True,                 # ETag-based optimistic locking
    auto_reload_on_conflict=False,       # reload from S3 on conflict
    check_etag_on_read=True,             # verify consistency on read
    upload_method="proxy",               # "proxy" or "single_put" (presigned URL)
    presigned_url_expiry=3600,           # URL expiry seconds
))
```

| Component | Backend |
|-----------|---------|
| Meta | SQLite stored in S3 |
| Revision | S3 objects |
| Blob | S3 |

**Best for**: cloud deployments, medium-scale, multi-node services.

### PostgresStorageFactory

All data in PostgreSQL. No external object storage needed.

```python
from autocrud.resource_manager.storage_factory import PostgresStorageFactory

crud.configure(storage_factory=PostgresStorageFactory(
    connection_string="postgresql://user:pass@host:5432/db",
    encoding="msgpack",          # msgpack recommended for PG (default)
    table_prefix="myapp_",      # prefix for table names
))
```

| Component | Backend |
|-----------|---------|
| Meta | PostgreSQL tables |
| Revision | PostgreSQL tables |
| Blob | PostgreSQL |

**Best for**: large-scale production, heavy query workloads, single-database architecture.

## Choosing a Backend

| Use Case | Recommended |
|----------|-------------|
| Unit tests | `MemoryStorageFactory` |
| Local development | `DiskStorageFactory` |
| Simple production | `DiskStorageFactory` |
| Cloud storage | `S3StorageFactory` |
| Large-scale production | `PostgresStorageFactory` |

## Per-Model Storage Override

Different resources can use different storage backends:

```python
crud.configure(storage_factory=DiskStorageFactory("./data"))  # default

crud.add_model(User)                                           # uses Disk
crud.add_model(Image, storage=S3StorageFactory(bucket="imgs")) # uses S3
crud.add_model(Config, storage=MemoryStorageFactory())         # uses Memory
```

## Storage Upgrade Path

```python
# Phase 1: Development/Testing
crud.configure(storage_factory=MemoryStorageFactory())

# Phase 2: Local persistence
crud.configure(storage_factory=DiskStorageFactory("./data"))

# Phase 3: Cloud deployment
crud.configure(storage_factory=S3StorageFactory(bucket="prod", endpoint_url=None))

# Phase 4: Large-scale production
crud.configure(storage_factory=PostgresStorageFactory(
    connection_string="postgresql://...",
))
```

---

## Message Queue System

AutoCRUD integrates async job processing directly into the resource model. Jobs are resources with status tracking, retry logic, and audit history.

### Message Queue Factories

```python
# In-process (default) — no infrastructure needed
from autocrud.message_queue.simple import SimpleMessageQueueFactory
crud.configure(message_queue_factory=SimpleMessageQueueFactory())

# RabbitMQ — distributed, production-ready
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueueFactory
crud.configure(message_queue_factory=RabbitMQMessageQueueFactory())

# Celery — distributed via Celery workers
from autocrud.message_queue.celery_queue import CeleryMessageQueueFactory
crud.configure(message_queue_factory=CeleryMessageQueueFactory(broker="redis://..."))
```

### Job Model Definition

Jobs are resources that automatically get queued when created:

```python
from msgspec import Struct
from autocrud.types import Job

class TaskPayload(Struct):
    query: str
    priority: int = 1

class TaskArtifact(Struct):
    result: str
    processing_time: float

# Job[T] is a special Struct with: payload (T), status, retries, max_retries, errmsg
class ProcessTask(Job[TaskPayload]):
    pass
```

### Job Handler

```python
from autocrud.types import Resource, JobContext, DelayRetry

def handle_task(
    task_resource: Resource[ProcessTask],
    job_context: JobContext[TaskPayload, TaskArtifact],
):
    payload = task_resource.data.payload
    retries = task_resource.data.retries

    # Logging
    job_context.info(f"Processing: {payload.query}")
    job_context.warning("Low priority task")

    # Delay retry — re-enqueue after N seconds
    if external_service_unavailable():
        raise DelayRetry(delay_seconds=30)

    # Set result artifact
    job_context.set_artifact(TaskArtifact(
        result="done",
        processing_time=1.5,
    ))
```

### Registration & Consumption

```python
# Register with handler
crud.add_model(
    ProcessTask,
    indexed_fields=[("status", str)],
    job_handler=handle_task,
)

crud.apply(app)

# Start consuming (after apply)
rm = crud.get_resource_manager(ProcessTask)
rm.start_consume(block=False)  # background thread

# For custom create/update actions with async_mode="job"
rm.start_consume(
    block=False,
    custom_creation="all",    # consume all async create actions
    custom_update="all",      # consume all async update actions
)
# Or specific job names:
rm.start_consume(custom_creation=["create-char-job"])
```

### Creating Jobs via API

Jobs are created like any resource — `POST /process-task` with payload data. The MQ consumer picks them up automatically.

```python
# Programmatic job creation
with rm.using("admin", dt.datetime.now()):
    rm.create(ProcessTask(payload=TaskPayload(query="find users")))
```

### Job Status Tracking

Jobs track status automatically: `pending` → `running` → `completed` / `failed`. Query via:

```python
# Find running jobs
running = rm.search_resources(QB["status"].eq("running"))

# Find failed jobs
failed = rm.search_resources(QB["status"].eq("failed"))
```

---

## DependencyProvider

Controls how HTTP routes determine the current user and timestamp:

```python
from autocrud.crud.route_templates.basic import DependencyProvider

# Default (anonymous user, current time)
dp = DependencyProvider()

# Custom authentication
dp = DependencyProvider(
    get_user=get_current_user,    # FastAPI Depends-compatible function
    get_now=lambda: dt.datetime.now(),
)

crud.configure(dependency_provider=dp)
```

If `default_user` is set in `crud.configure()`, it replaces the DependencyProvider's default when no custom `get_user` was provided.

## Extras Installation

```bash
pip install autocrud                   # core only
pip install "autocrud[s3]"             # S3 storage
pip install "autocrud[postgresql]"     # PostgreSQL storage
pip install "autocrud[redis]"          # Redis meta store
pip install "autocrud[mq]"            # RabbitMQ
pip install "autocrud[celery]"        # Celery workers
pip install "autocrud[graphql]"       # GraphQL support
pip install "autocrud[cli]"           # CLI tools
pip install "autocrud[all]"           # everything
```
