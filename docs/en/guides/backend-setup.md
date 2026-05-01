# Backend setup: metadata, resources, blobs, and jobs

For most real projects, the first important adoption step is not route generation.
It is choosing where your backend state will live.

This guide intentionally shows **two setup levels**:

1. the higher-level `backend=` API for a unified backend configuration story
2. the lower-level factory path for teams that want finer control over storage and queue wiring

Both are valid and fully supported. This guide starts with the higher-level backend API because it keeps the backend story unified, then moves to factories for cases that need more explicit control.

SpecStar separates backend setup into four concerns:

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
from specstar import BackendBinding, BackendConfig, ConnectionProfile, Schema, crud

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

crud.add_model(Schema(User, "v1"))
crud.apply(app)
```

That order keeps metadata, resource data, blob behavior, and queue behavior aligned from the beginning. The lower-level `storage_factory=` and `message_queue_factory=` arguments still work well when you want more explicit composition in Python.

---

## Two setup levels at a glance

| Level | Entry point | Best for | Tradeoff |
| --- | --- | --- | --- |
| higher-level | `crud.configure(backend=...)` | most projects, shared config files, easier onboarding | less explicit low-level wiring in user code |
| lower-level | `crud.configure(storage_factory=..., message_queue_factory=...)` | advanced deployments and precise backend composition | more setup detail and more concepts to manage |

## Recommended starting points

| Situation | Recommended setup | Blob behavior | Queue choice |
| --- | --- | --- | --- |
| tests or throwaway demos | `backend=` with in-memory bindings | in memory | default simple queue is enough |
| local development / MVP | `backend=` with a `disk` connection | local filesystem under the same data root | `simple` queue if you use jobs |
| recommended production path | `backend=` with PostgreSQL metadata, disk resource storage, S3 blobs | S3 | RabbitMQ |
| object-storage-first production | `backend=` with PostgreSQL + S3 bindings | S3 | RabbitMQ or Celery |
| advanced custom composition | lower-level storage and queue factories | depends on your factory choice | depends on your queue factory |

A common progression is to begin with the unified backend API and move to the lower-level factories only when you need more explicit control.

---

## 1. Install the integrations you actually need

```bash
pip install "specstar[postgresql,s3,mq]"
```

Common combinations:

- `specstar[postgresql]` for PostgreSQL metadata and resource storage
- `specstar[s3]` for S3-compatible data and blob storage
- `specstar[mq]` for RabbitMQ or Celery queue backends

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
from specstar import crud

crud.configure(backend="./backend.json")
```

This keeps connection information centralized and makes it easier to share the same backend setup across environments. JSON values also support environment-variable expansion such as `${POSTGRES_DSN}`.

---

## 3. Local persistent setup for a real MVP

This is the simplest durable setup for a single-node deployment using the higher-level backend API.

```python
from fastapi import FastAPI
from msgspec import Struct

from specstar import BackendBinding, BackendConfig, ConnectionProfile, Schema, crud


class User(Struct):
    name: str
    email: str


app = FastAPI()

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

crud.add_model(Schema(User, "v1"))
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

from specstar import BackendBinding, BackendConfig, BackendDefaults, ConnectionProfile, Schema, crud


class Document(Struct):
    title: str
    content: str


app = FastAPI()

crud.configure(
    backend=BackendConfig(
        defaults=BackendDefaults(
            table_prefix="app_",
            blob_prefix="uploads/",
        ),
        connections={
            "pg": ConnectionProfile(
                type="postgres",
                options={"dsn": os.environ["POSTGRES_DSN"]},
            ),
            "blob-s3": ConnectionProfile(
                type="s3",
                options={
                    "bucket": os.environ["S3_BUCKET"],
                    "access_key_id": os.environ["AWS_ACCESS_KEY_ID"],
                    "secret_access_key": os.environ["AWS_SECRET_ACCESS_KEY"],
                    "endpoint_url": os.getenv("S3_ENDPOINT_URL"),
                },
            ),
            "jobs": ConnectionProfile(
                type="rabbitmq",
                options={"amqp_url": os.environ["RABBITMQ_URL"]},
            ),
        },
        meta=BackendBinding(use="pg"),
        resource=BackendBinding(
            type="disk",
            options={"rootdir": "./data"},
        ),
        blob=BackendBinding(use="blob-s3"),
        mq=BackendBinding(use="jobs"),
    )
)

crud.add_model(Schema(Document, "v1"))
crud.apply(app)
```

This production layout keeps:

- searchable metadata in PostgreSQL
- resource payloads on local or mounted disk
- blobs in S3-compatible storage
- RabbitMQ-backed job workers

If you prefer object storage for both resource payloads and blobs, use S3 for both the `resource` and `blob` bindings.

---

## 5. When to use the lower-level factory path

The factory-style configuration is still a strong option when you want explicit control over the storage and queue objects being wired into SpecStar.

```python
from specstar import crud
from specstar.message_queue import RabbitMQMessageQueueFactory
from specstar.resource_manager import PostgresDiskS3StorageFactory

crud.configure(
    storage_factory=PostgresDiskS3StorageFactory(
        connection_string="postgresql://user:pass@host:5432/appdb",
        rootdir="./data",
        s3_bucket="my-blob-bucket",
    ),
    message_queue_factory=RabbitMQMessageQueueFactory(),
)
```

Use this path when you want to:

- construct backend objects directly in Python
- expose advanced options through concrete factory classes
- control storage composition at a lower level than the unified config schema

If your team is deciding between the two styles, think of `backend=` as the easier unified entry point and factories as the deeper control surface.

---

## 6. Understand what each storage factory really does

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

## 7. Choose a queue only when jobs matter

If your app never uses `Job[...]` resources or background execution, you can keep the default simple setup.

When jobs matter:

- use `SimpleMessageQueueFactory()` for local development or same-process consumers
- use `RabbitMQMessageQueueFactory()` for a broker-backed worker fleet
- use `CeleryMessageQueueFactory()` if your platform already standardizes on Celery

A minimal local job setup looks like this:

```python
from specstar import Schema, crud
from specstar.message_queue import SimpleMessageQueueFactory
from specstar.resource_manager import DiskStorageFactory

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

## 8. First deployment checklist

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

## 9. What to read next

- [Backend configuration reference](/specstar/reference/backend-configuration)
- [Storage](/specstar/guides/storage)
- [From demo to production](/specstar/guides/from-demo-to-production)
- [Job Queue quickstart](/specstar/quickstart/job-queue)
- [Binary data](/specstar/howto/binary-data)
