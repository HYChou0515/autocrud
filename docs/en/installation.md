# Installation

AutoCRUD is designed for modern FastAPI projects and works with Python 3.11 or newer.

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
pip install autocrud
```

If you use `uv` to manage dependencies:

```bash
uv add autocrud
```

---

## Optional extras

Install only the integrations you need.

| Use case | Package spec |
| --- | --- |
| S3 support | `autocrud[s3]` |
| GraphQL routes | `autocrud[graphql]` |
| Message queue backends | `autocrud[mq]` |
| CLI tooling | `autocrud[cli]` |
| PostgreSQL support | `autocrud[postgresql]` |
| Redis support | `autocrud[redis]` |
| SQLAlchemy integration | `autocrud[sqlalchemy]` |
| Everything included | `autocrud[all]` |

Example:

```bash
pip install 'autocrud[graphql,mq]'
```

---

## Verify the installation

You can quickly verify that the package is available:

```bash
python -c "import autocrud; print(autocrud.__version__)"
```

If that command prints a version string, the installation is ready.

---

## Minimal usage example

```python
from fastapi import FastAPI
from msgspec import Struct

from autocrud import crud


class User(Struct):
    name: str
    email: str


app = FastAPI()
crud.add_model(User)
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

- [Fast demo](/autocrud/quickstart/fast-demo) if you want the quickest end-to-end example
- [Integrate with an existing FastAPI app](/autocrud/quickstart/integrate-existing) if you already have a project
- [Routes generation](/autocrud/howto/routes) if you want to understand what gets exposed automatically
