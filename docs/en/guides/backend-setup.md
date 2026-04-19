# Backend setup: metadata, resources, blobs, and jobs

For most real projects, the first important adoption step is not route generation.
It is choosing where your backend state will live.

AutoCRUD separates backend setup into four concerns:

| Concern | What it stores | Typical choices |
| --- | --- | --- |
| metadata store | resource IDs, revisions, search/index metadata, lifecycle state | memory, local disk, PostgreSQL, S3-backed SQLite |
| resource store | the structured resource payload itself | memory, disk, PostgreSQL, S3 |
| blob store | binary files, uploads, and job log artifacts | memory, local disk, S3 |
| message queue | background job delivery and retries | simple in-process, RabbitMQ, Celery |

If you choose these four pieces deliberately at the start, the rest of the product is much easier to adapt.

---

## The golden rule: configure first

Configure your backend before registering models.

```python
from autocrud import BackendBinding, BackendConfig, ConnectionProfile, crud

crud.configure(
    backend=BackendConfig(
        connections={
            "local": ConnectionProfile(
                type="disk",
                options={"rootdir": "./data"},
            )
        },
        meta=BackendBinding(use="local"),
        resource=BackendBinding(use="local"),
        blob=BackendBinding(use="local"),
    )
)

crud.add_model(User)
crud.apply(app)
```

That order keeps metadata, resource data, blob behavior, and queue behavior aligned from the beginning. The older `storage_factory=` and `message_queue_factory=` arguments still work, but `backend=` is now the preferred entry point.

---

## Recommended starting points

| Situation | Recommended setup | Blob behavior | Queue choice |
| --- | --- | --- | --- |
| tests or throwaway demos | `MemoryStorageFactory()` | in memory | default simple queue is enough |
| local development / MVP | `DiskStorageFactory("./data")` | local filesystem under the same data root | `SimpleMessageQueueFactory()` if you use jobs |
| recommended production path | `PostgresDiskS3StorageFactory(...)` | S3 | `RabbitMQMessageQueueFactory()` |
| alternative for object-storage-first deployments | `PostgreSQLS3StorageFactory(...)` | S3 | `RabbitMQMessageQueueFactory()` or `CeleryMessageQueueFactory()` |
| production without binary uploads | `PostgresStorageFactory(...)` | in memory by default, so only safe if you do not need durable blobs | optional |

If you are unsure, start with `DiskStorageFactory` locally and move to PostgreSQL + Disk + S3 blobs + RabbitMQ for production.

---

## 1. Install the integrations you actually need

```bash
pip install "autocrud[postgresql,s3,mq]"
```

Common combinations:

- `autocrud[postgresql]` for PostgreSQL metadata and resource storage
- `autocrud[s3]` for S3-compatible data and blob storage
- `autocrud[mq]` for RabbitMQ or Celery queue backends

If you only need local persistence, the base package plus `DiskStorageFactory` is often enough.

---

## 2. JSON config-file setup

If you want deployment-friendly backend setup, place the unified config in a JSON file and load it directly.

```json
{
  "version": 1,
  "connections": {
    "local": {
      "type": "disk",
      "options": {
        "rootdir": "./data"
      }
    },
    "jobs": {
      "type": "simple",
      "options": {
        "max_retries": 3
      }
    }
  },
  "meta": {"use": "local"},
  "resource": {"use": "local"},
  "blob": {"use": "local"},
  "mq": {"use": "jobs"}
}
```

```python
from autocrud import crud

crud.configure(backend="./backend.json")
```

This keeps connection information centralized and makes it easier to share the same backend setup across environments.

---

## 3. Local persistent setup for a real MVP

This is the simplest durable setup for a single-node deployment.

```python
from fastapi import FastAPI
from msgspec import Struct

from autocrud import crud
from autocrud.resource_manager import DiskStorageFactory


class User(Struct):
    name: str
    email: str


app = FastAPI()

crud.configure(
    storage_factory=DiskStorageFactory("./data"),
)

crud.add_model(User)
crud.apply(app)
```

What this gives you:

- persistent metadata on local disk
- persistent resource payloads on local disk
- persistent blobs under the same local data area
- no extra infrastructure to operate

Use this when you want the fastest path from demo to something your team can restart safely.

---

## 4. Recommended production setup

The current recommended production shape is:

- PostgreSQL for searchable metadata
- Disk for resource payload storage
- S3 for durable blobs and uploaded files
- RabbitMQ for background workers

```python
import os

from fastapi import FastAPI
from msgspec import Struct

from autocrud import crud
from autocrud.message_queue import RabbitMQMessageQueueFactory
from autocrud.resource_manager import PostgresDiskS3StorageFactory


class Document(Struct):
    title: str
    content: str


app = FastAPI()

crud.configure(
    storage_factory=PostgresDiskS3StorageFactory(
        connection_string=os.environ["POSTGRES_DSN"],
        rootdir="./data",
        s3_bucket=os.environ["S3_BUCKET"],
        s3_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        s3_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        s3_endpoint_url=os.getenv("S3_ENDPOINT_URL"),
        table_prefix="app_",
    ),
    message_queue_factory=RabbitMQMessageQueueFactory(),
)

crud.add_model(Document)
crud.apply(app)
```

This production layout keeps:

- searchable metadata in PostgreSQL
- resource payloads on local or mounted disk
- blobs in S3-compatible storage
- RabbitMQ-backed job workers

If you prefer object storage for both resource payloads and blobs, `PostgreSQLS3StorageFactory(...)` remains a valid alternative.

---

## 5. Understand what each storage factory really does

The easiest way to avoid surprises is to map the factory to the four backend concerns.

| Factory | Metadata | Resource data | Blob data |
| --- | --- | --- | --- |
| `MemoryStorageFactory()` | memory | memory | memory |
| `DiskStorageFactory("./data")` | disk-backed metadata | local files | local files |
| `S3StorageFactory(...)` | SQLite synced to S3 | S3 | S3 |
| `PostgresStorageFactory(...)` | PostgreSQL | PostgreSQL | memory by default |
| `PostgreSQLS3StorageFactory(...)` | PostgreSQL | S3 | S3 |
| `PostgresDiskStorageFactory(...)` | PostgreSQL | local disk | memory by default |
| `PostgresDiskS3StorageFactory(...)` | PostgreSQL | local disk | S3 |

Two important consequences:

1. If your resource includes binary uploads, do not assume every PostgreSQL-based setup automatically persists blobs.
2. The current recommended production shape is `PostgresDiskS3StorageFactory(...)` together with `RabbitMQMessageQueueFactory()` for workers.

---

## 6. Choose a queue only when jobs matter

If your app never uses `Job[...]` resources or background execution, you can keep the default simple setup.

When jobs matter:

- use `SimpleMessageQueueFactory()` for local development or same-process consumers
- use `RabbitMQMessageQueueFactory()` for a broker-backed worker fleet
- use `CeleryMessageQueueFactory()` if your platform already standardizes on Celery

A minimal local job setup looks like this:

```python
from autocrud import Schema, crud
from autocrud.message_queue import SimpleMessageQueueFactory
from autocrud.resource_manager import DiskStorageFactory

crud.configure(
    storage_factory=DiskStorageFactory("./data"),
    message_queue_factory=SimpleMessageQueueFactory(),
)

crud.add_model(Schema(TrainingJob, "v1"), job_handler=training)

mgr = crud.get_resource_manager(TrainingJob)
mgr.start_consume(block=False)
```

If jobs stay in `pending`, check that:

- the queue backend is configured
- a consumer or worker is actually running
- the broker is reachable from the process that handles jobs

---

## 7. First deployment checklist

Before calling your backend ready for adoption, verify all of the following:

- the app uses `crud.configure(...)` before `add_model(...)`
- restarts do not lose metadata or resource payloads
- binary uploads still exist after restart or redeploy
- any required worker process is running for job execution
- the chosen extras are installed for the selected backend
- one create, one search, and one blob upload succeed in the target environment

A quick persistence smoke test is simple:

1. create one resource
2. restart the app
3. fetch the same resource again
4. if you use blobs, upload one file and download it after restart

---

## 8. What to read next

- [Storage](/autocrud/guides/storage)
- [From demo to production](/autocrud/guides/from-demo-to-production)
- [Job Queue quickstart](/autocrud/quickstart/job-queue)
- [Binary data](/autocrud/howto/binary-data)
