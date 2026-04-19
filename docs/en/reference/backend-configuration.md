# Backend configuration reference

This page is the lookup reference for AutoCRUD backend settings.

It covers both supported setup levels:

- the higher-level unified API via `crud.configure(backend=...)`
- the lower-level factory path via `storage_factory=` and `message_queue_factory=`

The guide pages focus on workflow. This page focuses on the settings surface.

---

## Two setup levels

| Level | Entry point | Strength | Best fit |
| --- | --- | --- | --- |
| higher-level | `backend=` | one unified config story for metadata, resources, blobs, and queues | most applications, JSON config files, deployment-friendly setup |
| lower-level | `storage_factory=` + `message_queue_factory=` | more direct construction and lower-level control | advanced Python-first composition and custom backend wiring |

---

## Unified backend model

The unified backend API is built from four public types:

| Type | Purpose |
| --- | --- |
| `BackendDefaults` | shared defaults reused across providers |
| `ConnectionProfile` | a named reusable backend connection |
| `BackendBinding` | maps one role to either a named connection or an inline backend type |
| `BackendConfig` | the top-level object combining defaults, connections, and bindings |

The four backend roles are:

- `meta` — metadata store
- `resource` — structured resource payload store
- `blob` — file/blob storage
- `mq` — message queue

Example:

```python
from autocrud import BackendBinding, BackendConfig, ConnectionProfile, crud

crud.configure(
    backend=BackendConfig(
        connections={
            "local": ConnectionProfile(
                type="disk",
                options={"rootdir": "./data"},
            ),
            "jobs": ConnectionProfile(
                type="simple",
                options={"max_retries": 3},
            ),
        },
        meta=BackendBinding(use="local"),
        resource=BackendBinding(use="local"),
        blob=BackendBinding(use="local"),
        mq=BackendBinding(use="jobs"),
    )
)
```

---

## Resolution and override rules

When AutoCRUD resolves `backend=...`, it applies these rules:

1. the value may be a `BackendConfig` object, a plain mapping, or a JSON file path
2. environment variables inside strings are expanded automatically
3. when a binding uses `use="name"`, the connection's `options` are merged with the binding's `options`
4. binding-level `options` override connection-level `options` when both define the same key
5. shared defaults in `BackendDefaults` are consulted by providers for fields such as encoding, table prefixes, blob prefixes, upload style, and presigned URL expiry
6. the selected provider must support the requested role

If `mq` is omitted, no message queue factory is created.

---

## Shared defaults

`BackendDefaults` fields are reused across the providers that support them.

| Field | Default | Used by |
| --- | --- | --- |
| `encoding` | `json` | memory, disk, postgres, s3 resource/meta providers |
| `table_prefix` | `""` | postgres metadata and resource tables |
| `blob_prefix` | `"blobs/"` | s3 blob storage |
| `upload_method` | `"proxy"` | s3 blob uploads |
| `presigned_url_expiry` | `3600` | s3 blob uploads |

Example:

```python
from autocrud import BackendBinding, BackendConfig, BackendDefaults

config = BackendConfig(
    defaults=BackendDefaults(
        table_prefix="app_",
        blob_prefix="uploads/",
        presigned_url_expiry=900,
    ),
    meta=BackendBinding(type="memory"),
    resource=BackendBinding(type="memory"),
    blob=BackendBinding(type="memory"),
)
```

---

## Built-in backend types

| Type | Supported roles | Required options | Notes |
| --- | --- | --- | --- |
| `memory` | `meta`, `resource`, `blob` | none | best for tests and throwaway demos |
| `disk` | `meta`, `resource`, `blob` | `rootdir` | local persistence under one root directory |
| `postgres` | `meta`, `resource` | `dsn` or `connection_string` | query-friendly SQL-backed storage |
| `s3` | `meta`, `resource`, `blob` | `bucket` | works with AWS S3 and S3-compatible endpoints |
| `simple` | `mq` | none | in-process queue factory |
| `rabbitmq` | `mq` | none | broker-backed queue with configurable AMQP URL |

---

## Provider option reference

### `disk`

| Option | Required | Meaning |
| --- | --- | --- |
| `rootdir` | yes | root directory for metadata, resource payloads, and `_blobs/` |
| `encoding` | no | inherits from `defaults.encoding` when relevant |

### `postgres`

| Option | Required | Meaning |
| --- | --- | --- |
| `dsn` | yes* | PostgreSQL DSN |
| `connection_string` | yes* | accepted alias for `dsn` |
| `table_prefix` | no | overrides `defaults.table_prefix` |
| `encoding` | no | overrides `defaults.encoding` |

> `dsn` or `connection_string` must be provided.

### `s3`

| Option | Required | Meaning |
| --- | --- | --- |
| `bucket` | yes | main bucket for metadata/resource storage |
| `blob_bucket` | no | separate bucket for blobs; defaults to `bucket` |
| `prefix` | no | prefix used for metadata and resource keys |
| `blob_prefix` | no | prefix used for blob keys; falls back to `defaults.blob_prefix` |
| `access_key_id` / `s3_access_key_id` | no | S3 access key |
| `secret_access_key` / `s3_secret_access_key` | no | S3 secret key |
| `region_name` / `s3_region` | no | region name; defaults to `us-east-1` |
| `endpoint_url` / `s3_endpoint_url` | no | custom endpoint, such as MinIO |
| `client_kwargs` / `s3_client_kwargs` | no | extra S3 client options |
| `encoding` | no | overrides `defaults.encoding` |
| `auto_sync` | no | metadata sync behavior for the S3-backed SQLite meta store; default `True` |
| `sync_interval` | no | periodic sync interval; default `0` |
| `enable_locking` | no | enable ETag-based locking; default `True` |
| `auto_reload_on_conflict` | no | reload metadata on conflict; default `False` |
| `check_etag_on_read` | no | validate ETag during reads; default `True` |
| `upload_method` | no | blob upload style; defaults to `defaults.upload_method` |
| `presigned_url_expiry` | no | expiry in seconds for blob uploads; defaults to `defaults.presigned_url_expiry` |

### `simple` message queue

| Option | Default | Meaning |
| --- | --- | --- |
| `max_retries` | `3` | retry count for in-process job handling |

### `rabbitmq`

| Option | Default | Meaning |
| --- | --- | --- |
| `amqp_url` | `amqp://guest:guest@localhost:5672/` | broker connection URL |
| `queue_prefix` | `autocrud:` | queue naming prefix |
| `max_retries` | `3` | job retry count |
| `retry_delay_seconds` | `10` | delay before retry |
| `amqp_heartbeat_seconds` | `600` | heartbeat interval |

---

## Environment-variable expansion

Environment variables are expanded automatically when `backend=` is loaded from a JSON file or a plain mapping.

```json
{
  "connections": {
    "pg": {
      "type": "postgres",
      "options": {
        "dsn": "${POSTGRES_DSN}"
      }
    },
    "blob-s3": {
      "type": "s3",
      "options": {
        "bucket": "${S3_BUCKET}",
        "endpoint_url": "${S3_ENDPOINT_URL}"
      }
    }
  },
  "meta": {"use": "pg"},
  "resource": {"use": "pg"},
  "blob": {"use": "blob-s3"}
}
```

This makes it practical to keep secrets and environment-specific values outside the repository.

---

## Lower-level factory path

The factory path stays useful when you want to construct the exact backend objects yourself.

```python
from autocrud import crud
from autocrud.message_queue import RabbitMQMessageQueueFactory
from autocrud.resource_manager import PostgresDiskS3StorageFactory

crud.configure(
    storage_factory=PostgresDiskS3StorageFactory(
        connection_string="postgresql://user:pass@host:5432/appdb",
        rootdir="./data",
        s3_bucket="my-blob-bucket",
    ),
    message_queue_factory=RabbitMQMessageQueueFactory(),
)
```

Use this path when you want:

- direct construction in Python instead of schema-style config
- fine-grained storage composition through concrete factory classes
- per-model storage overrides with explicit factory instances

---

## Related pages

- [Backend setup](/autocrud/guides/backend-setup)
- [Storage backends](/autocrud/guides/storage)
- [Behavior & initialization](/autocrud/reference/behavior)
- [Job Queue quickstart](/autocrud/quickstart/job-queue)
