# Installation

SpecStar is designed for modern FastAPI projects and works with Python 3.11 or newer.

For most applications, the base package is enough to get started. Optional extras are available for storage backends, GraphQL, queues, and CLI utilities.

---

## Requirements

Before installing, make sure your environment has:

- Python 3.11+
- FastAPI 0.115+
- a virtual environment recommended for local development

---

## Basic installation

Install the core package with pip:

```bash
pip install specstar
```

If you use `uv` to manage dependencies:

```bash
uv add specstar
```

---

## Optional extras

Install only the integrations you need.

| Use case | Package spec |
| --- | --- |
| S3 support | `specstar[s3]` |
| GraphQL routes | `specstar[graphql]` |
| Message queue backends | `specstar[mq]` |
| CLI tooling | `specstar[cli]` |
| PostgreSQL support | `specstar[postgresql]` |
| Redis support | `specstar[redis]` |
| SQLAlchemy integration | `specstar[sqlalchemy]` |
| Everything included | `specstar[all]` |

Example:

```bash
pip install 'specstar[graphql,mq]'
```

### Common backend bundles

Use a bundle that matches your deployment stage:

| Goal | Recommended install |
| --- | --- |
| local MVP with durable files | `pip install specstar` |
| PostgreSQL-backed API | `pip install 'specstar[postgresql]'` |
| object storage and blob uploads | `pip install 'specstar[s3]'` |
| production jobs and workers | `pip install 'specstar[mq]'` |
| recommended production stack | `pip install 'specstar[postgresql,s3,mq]'` |

The recommended production stack is `PostgresDiskS3StorageFactory(...)` plus `RabbitMQMessageQueueFactory()`.

If you are not sure which one to choose, continue with the [backend setup guide](/specstar/guides/backend-setup).

---

## Verify the installation

You can quickly verify that the package is available:

```bash
python -c "import specstar; print(specstar.__version__)"
```

If that command prints a version string, the installation is ready.

---

## Configure the default list limit

List-style endpoints are paginated by default. You can control the startup default
with the `AUTOCRUD_DEFAULT_QUERY_LIMIT` environment variable.

Example:

```bash
export AUTOCRUD_DEFAULT_QUERY_LIMIT=1000
uvicorn main:app --reload
```

Notes:

- if unset, SpecStar falls back to a very large default first page size
- a request-level `limit` still overrides the startup default
- if you need an exact total count, use the `/count` endpoint

---

## Minimal usage example

```python
from fastapi import FastAPI
from msgspec import Struct

from specstar import crud, Schema


class User(Struct):
    name: str
    email: str


app = FastAPI()
crud.configure()
crud.add_model(Schema(User, "v1"))
crud.apply(app)
```

Run the server:

```bash
uvicorn main:app --reload
```

Then open:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

---

## Choose your next step

- [Fast demo](/specstar/quickstart/fast-demo) if you want the quickest end-to-end example
- [Backend setup](/specstar/guides/backend-setup) if you need to choose metadata, resource, blob, or queue backends
- [Integrate with an existing FastAPI app](/specstar/quickstart/integrate-existing) if you already have a project
- [Routes generation](/specstar/howto/routes) if you want to understand what gets exposed automatically
