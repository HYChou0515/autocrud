# From Demo to Production

SpecStar works well with in-memory backends for demos, tests, and early experiments.
That setup optimizes for speed and convenience, not durability.

Once the project needs persistent data, repeatable deployments, background workers, or
binary uploads, you should move to production-oriented backends.

---

## What changes in production

In most demo setups, everything is kept in memory.

That is fine when:

* data loss on restart is acceptable
* only one process is running
* background work is not critical
* uploaded files are disposable

That is usually **not** acceptable in production.

For a production deployment, review these areas:

* persistence backend for metadata and revisions
* blob storage for binary files
* message queue backend for background jobs
* backup and restore procedures

---

## 1. Replace memory storage

If you are using `MemoryStorageFactory`, all data disappears when the process exits.

For production, choose a persistent backend instead.

Recommended starting points:

| Situation | Recommended choice |
| --------- | ------------------ |
| local or single-node deployment | `DiskStorageFactory` |
| recommended production deployment | `PostgresDiskS3StorageFactory` + `RabbitMQMessageQueueFactory` |
| cloud deployment with object storage for all payloads | `PostgreSQLS3StorageFactory` |
| PostgreSQL-centric API without durable uploads | `PostgresStorageFactory` |

Rule of thumb:

* use memory for tests and demos
* use disk for simple local systems
* use PostgreSQL + Disk + S3 blobs + RabbitMQ for the default production path
* use PostgreSQL + S3 when you specifically want object storage for resource payloads too

If you need a deeper comparison, see the [storage guide](/specstar/guides/storage).

---

## 2. Choose a queue only if you run background jobs

Not every SpecStar application needs a message queue.

If all requests are handled synchronously, you can deploy without one.

You should configure a queue when:

* you use job-style processing
* work should continue after the HTTP request returns
* retries and worker isolation matter
* long-running tasks should not block API responses

Typical choices are:

* `SimpleMessageQueue` for local development or simple single-process setups
* `RabbitMQMessageQueue` for distributed worker deployments
* `CeleryMessageQueue` if your platform already standardizes on Celery

When you add a queue, remember that production also needs worker processes that consume jobs.

---

## 3. Plan blob storage for binary data

If your resources include uploaded files, images, or other binary payloads, blob storage
becomes a production decision too.

For small single-node deployments, filesystem-based storage is often enough.

For multi-node or cloud deployments, prefer shared object storage such as S3-compatible
storage so application instances can stay stateless.

If your deployment uses `PostgresStorageFactory`, remember that binary-upload durability
is still a separate decision. For file-heavy systems, prefer `DiskStorageFactory`,
`S3StorageFactory`, or `PostgreSQLS3StorageFactory`.

This matters for:

* file durability
* horizontal scaling
* backup strategy
* operational simplicity

---

## 4. Move demo data into production

You do not need to throw away demo data.

SpecStar provides two migration paths:

* per-model export/import routes
* global backup/restore routes

Per-model export/import is useful when you only want to move selected resources.

* `GET /{model_name}/export`
* `POST /{model_name}/import`

Global backup/restore is useful when you want to move a full environment or multiple models
at once.

* `GET /_backup/export`
* `POST /_backup/import`

Typical migration flow:

1. Keep the demo environment running.
2. Export the data you want to preserve.
3. Start a new deployment with production backends.
4. Import the archive into the new environment.
5. Verify references, search behavior, and blob accessibility.

For large datasets, treat export/import like an operational migration task rather than an
interactive admin action.

---

## 5. Production checklist

Before calling a system production-ready, verify that:

* restarts do not lose data
* backups can be restored successfully
* workers are running if jobs are enabled
* blob files remain accessible after redeployments
* the selected backend matches expected scale and query volume

The main transition is simple:

> Keep the SpecStar model and API shape.
> Replace demo backends with production backends.
> Use export/import or backup/restore to move the data.

That lets you evolve a prototype into a production system without rewriting the application model.