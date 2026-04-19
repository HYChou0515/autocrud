# Examples

This page helps you find the most useful runnable examples in the repository.

If you want to learn AutoCRUD by copying a working project instead of starting from a blank file, begin here.

If your first question is how to choose metadata, resource, blob, and queue backends, read the [backend setup guide](/autocrud/guides/backend-setup) before picking a production-style example.

---

## Recommended order

If you are new to the project, this is the suggested reading and running order:

1. basic FastAPI example
2. Pydantic-based example
3. S3 storage example
4. PostgreSQL + S3 production-style example
5. Celery queue example

---

## Example map

| Example | What it demonstrates | Run command |
| --- | --- | --- |
| [Basic RPG API](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_api.py) | core CRUD setup, refs, search, GraphQL, blobs, migrations, custom actions | `uv run python examples/rpg_game_api.py` |
| [Pydantic RPG API](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_pydantic_api.py) | using Pydantic models, validators, discriminated unions, GraphQL, blob support | `uv run python examples/rpg_game_pydantic_api.py` |
| [S3 backend example](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_s3_api.py) | object storage for data and binary files, MinIO or AWS-style deployment | `uv run python examples/rpg_game_s3_api.py` |
| [PostgreSQL + S3 example](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_postgres_s3_api.py) | production-oriented metadata queries in PostgreSQL with data and blobs stored in S3 | `uv run python examples/rpg_game_postgres_s3_api.py` |
| [Celery queue example](https://github.com/HYChou0515/autocrud/blob/master/examples/rpg_game_celery_api.py) | distributed background jobs, Redis broker, worker-based processing | `uv run python examples/rpg_game_celery_api.py` |

---

## Which example should you choose?

### Choose the basic RPG API if you want:

- the fastest path to understanding AutoCRUD
- a broad overview of features in one file
- an example that matches the main documentation flow

### Choose the Pydantic example if you already use:

- `BaseModel`
- field validators
- discriminated unions
- Pydantic-first application design

### Choose the S3 or PostgreSQL + S3 examples if you need:

- persistent storage
- production-like deployment patterns
- blob and binary file workflows
- object storage or MinIO compatibility

### Choose the Celery example if you need:

- worker-based background jobs
- retry and queue patterns
- asynchronous event processing

---

## After starting an example

Most examples expose a FastAPI application, so the next step is usually to open:

- `http://localhost:8000/docs`

Then compare what you see with these guides:

- [Routes generation](/autocrud/howto/routes)
- [Permissions](/autocrud/howto/permissions)
- [Event handlers](/autocrud/howto/event-handlers)
- [Query builder](/autocrud/howto/query-builder)
- [GraphQL](/autocrud/howto/graphql)
- [Binary data](/autocrud/howto/binary-data)
