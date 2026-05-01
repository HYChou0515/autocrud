# Quickstart - Async Action

In this quickstart, we will show how to run actions asynchronously in SpecStar.

SpecStar allows you to turn normal create/update actions into background tasks  
without changing your business logic.

---

## What problem does this solve?

In real applications, some operations:

- take a long time (e.g. model training, file processing)
- should not block the request
- may need to run in the background or via a job queue

Instead of manually wiring:

- background workers
- task queues
- API + async orchestration

SpecStar lets you switch execution mode with a single parameter.

---

## Execution modes

SpecStar supports three execution modes:

| mode | behavior |
|------|--------|
| `sync` (default) | run immediately in request |
| `background` | run in FastAPI background task |
| `job` | run via job queue (with retry, log, etc.) |

---

## 1. Define an action

You can define custom actions using decorators like `create_action` or `update_action`.

```python
@crud.create_action(
    "character",
    label="Create Character",
)
async def create_character():
    return Character(name="Alice")
```

This automatically generates:

- an API endpoint
- request parsing (body / params)
- OpenAPI schema

The parameter handling follows FastAPI behavior.

---

## 2. Run in background (non-blocking)

To avoid blocking the request, set:

```python
async_mode="background"
```

```python
@crud.create_action(
    "character",
    label="Create Character (background)",
    async_mode="background",
)
async def create_character_background():
    import time

    time.sleep(5)

    return Character(name="background")
```

### Behavior

- request returns immediately
- task runs in background
- no job tracking (lightweight)

Use this when:

- you just need non-blocking execution
- you don’t need retry / logs / status tracking

---

## 3. Run as job (full job system)

For long-running or important tasks, use:

```python
async_mode="job"
```

```python
@crud.create_action(
    "character",
    label="Create Character (job)",
    async_mode="job",
)
async def create_character_job():
    import time

    time.sleep(10)

    return Character(name="job")
```

### Behavior

- task is submitted to job queue
- supports retry / logs / rerun
- trackable via job system

Use this when:

- task is long-running
- you need observability
- you need retry or failure handling

👉 See: [Job Queue](/specstar/quickstart/job-queue)

---

## 4. Example: update with background execution

```python
@crud.update_action(
    "character",
    label="Update Name",
    async_mode="background",
)
async def update_char_name(existing: Character, info: RevisionInfo):
    import time

    time.sleep(5)
    existing.name = f"{time.time()} ({info.updated_time})"
    return existing
```

---

## 5. Request → function mapping

SpecStar uses FastAPI’s parameter parsing.

This means:

- function parameters → request schema
- body / query / path are auto-detected
- OpenAPI is generated automatically

Example:

```python
@crud.create_action(
    "character",
    label="Complex Input",
    async_mode="job",
)
async def create_character_complex(
    x: int | str,
    name: Annotated[str, Body(embed=True)],
    file: UploadFile,
):
    return Character(name=f"{name} ({x})")
```

This will automatically generate:

- request body
- file upload support
- OpenAPI schema

---

## 6. Generated routes

Actions generate endpoints automatically.

For example:

```python
@crud.create_action("character", label="New Character")
```

will generate:

```
POST /character/new-character
```

The route is derived from:

- resource name (`character`)
- action name (`new-character`)

---

## 7. Choosing the right mode

| scenario | mode |
|--------|------|
| quick operation | `sync` |
| avoid blocking API | `background` |
| long-running / important task | `job` |

---

## 8. Summary

With SpecStar async actions, you can:

- define business logic as normal Python functions
- expose them as APIs automatically
- switch execution mode without changing code structure

This allows you to:

- start simple (`sync`)
- move to background (`background`)
- scale to full job system (`job`)

---

## Next Steps

If you decide to run actions in `job` mode, the next step is to configure the backend and queue setup so workers have a real execution path.

- [Set up backend persistence and queue choices](/specstar/guides/backend-setup)
- [Job Queue](/specstar/quickstart/job-queue)
- [Integrate Existing](/specstar/quickstart/integrate-existing)