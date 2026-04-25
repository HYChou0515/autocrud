# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AutoCRUD (v0.8.3) is a model-driven backend platform for FastAPI. Define a `msgspec.Struct` model once; the framework generates REST APIs, GraphQL, search, version history, permissions, background jobs, and an admin UI automatically.

## Commands

**Always use `uv run` to execute scripts in the project environment.**

```bash
make test          # lint + run tests (excluding benchmarks) + coverage report
make style         # auto-format: ruff format + ruff check --fix (run before committing)
make check         # lint only: ruff check + ruff format --check
make dev           # quick dev cycle: style + test
make coverage      # run tests + coverage report (target ≥90%)
make ci            # CI gate: check + test + coverage
make build         # uv build
make docs          # build MkDocs docs
make serve         # serve docs locally
```

**Run a single test:**
```bash
uv run pytest tests/test_autocrud.py::TestAutocrud::test_add_model_with_encoding -v
uv run pytest tests/ -k "test_add_model" -v
```

## Architecture

### Core Components

- **`AutoCRUD`** (`autocrud/crud/core.py`): Entry point — model registration + route generation.
  - **Global Instance** (recommended): `from autocrud import crud` → `crud.configure()` → `crud.add_model()`
  - **Manual Instance**: `AutoCRUD()` constructor for multiple independent instances
- **`ResourceManager`** (`autocrud/resource_manager/core.py`): Core business logic — CRUD, versioning, permissions, events, migration, unique constraints, data coercion.
- **Route Templates** (`autocrud/crud/route_templates/`): Each template generates specific API endpoints.
  - Basic: `create`, `read`, `update`, `delete`, `search`, `patch`, `switch`
  - Advanced: `blob`, `graphql`, `migrate`, `backup`, `rerun`, `batch_delete`, `batch_restore`, `restore`, `permanently_delete`
- **Schema API** (`autocrud/schema.py`): Unified migration + validation with fluent `.step()` / `.plus()` chain API. Uses BFS to find shortest migration path between versions.
- **Query Builder** (`autocrud/query.py` + `autocrud/crud/qb_parser.py`): Django-like query API with operator overloading (`==`, `!=`, `>=`, `&`, `|`, `~`).
- **Storage Abstraction** — three independent layers, each with multiple backends:
  - `IMetaStore`: simple (memory), postgres, redis, sqlalchemy, sqlite3, df, fast_slow
  - `IResourceStore`: simple (memory), s3, cache, cached_s3, etag_cached_s3, mq_cached_s3, postgres
  - `IBlobStore`: simple (memory), s3
  - `IStorageFactory` (`autocrud/resource_manager/storage_factory.py`) creates per-model storage instances.
- **Permission System** (`autocrud/permission/`): ACL, RBAC, action-based, data-based, meta-based, composite.
- **Message Queue** (`autocrud/message_queue/`): Simple, RabbitMQ, Celery backends + heartbeat.
- **Pydantic Converter** (`autocrud/resource_manager/pydantic_converter.py`): Bidirectional `pydantic_to_struct()` / `struct_to_pydantic()`.

### Key Architectural Patterns

- **Versioning**: Every modification creates a new immutable revision. Status: `draft` (mutable) or `stable` (immutable). Parent-child chains enable full history.
- **Data Coercion**: `_coerce_data()` accepts `dict`, `Struct`, or Pydantic `BaseModel` → **always outputs `msgspec.Struct` internally**. Never return Pydantic instances from `ResourceManager` methods — `MsgspecResponse.render()` only supports Struct.
- **UNSET Pattern**: Use `msgspec.UNSET` / `UnsetType` to distinguish "not provided" from `None`.
- **Soft Delete**: `DeleteRouteTemplate` is soft-delete; use `RestoreRouteTemplate` / `PermanentlyDeleteRouteTemplate` for recovery.
- **Unique Constraints**: `Unique` annotation + `UniqueConstraintHandler` (`autocrud/resource_manager/unique_handler.py`).

### Public API

Only exports from `autocrud/__init__.py` are public: `AutoCRUD`, `crud`, `Schema`, `LoadStats`, `struct_to_pydantic`, `DisplayName`, `Unique`, `UniqueConstraintError`, `IConstraintChecker`, `IValidator`, `ValidationError`, `DuplicateResourceError`, `OnDelete`, `OnDuplicate`, `Ref`, `RefRevision`, `RefType`, `RevisionNotMigratedError`, `SearchedResource`, `ResourceOps`, `BackgroundTaskAccepted`, `BlobUploadSession`, `JobRedirectInfo`, `MissingOperationContextError`.

## Coding Conventions

### Data Models

Use `msgspec.Struct` for all models. Pydantic models are accepted as input and auto-converted.

```python
from msgspec import Struct, UNSET, UnsetType

class User(Struct):
    name: str
    age: int
    email: str | None = None

class PatchUser(Struct, kw_only=True):
    name: str | UnsetType = UNSET   # distinguishes "not provided" from None
```

### Schema API

```python
from autocrud import Schema

schema = Schema(UserV2, "v2").step("v1", migrate_v1_to_v2).plus(validator_fn)
crud.add_model(User, schema=schema)
```

### General

- Extensive type hints required — `typing_extensions.Literal`, `Generic[T]`, etc.
- All FastAPI routes and storage operations are `async`.
- Google-style docstrings; write `TODO` for unclear items rather than guessing.
- Code and comments in English; always respond to the user in 台灣繁體中文.
- All new features must update docstrings and documentation.

## Testing

- All new features must include tests targeting **≥90% coverage**.
- Bug fixes follow TDD: write failing test → implement fix → verify → refactor.
- Use `msgspec.Struct` for test models.
- Only run your own tests — avoid running unrelated test suites.
- Frontend tests: run `pnpm test` under `web/app/` and confirm they pass.
- Key test directories: `tests/test_autocrud.py` (integration), `tests/test_schema.py`, `tests/routes/` (API), `tests/meta_store/` (storage), `tests/permission/`.

## Component Skills

Detailed implementation guides live in `.claude/skills/`. Consult the relevant skill before modifying or extending a component:

| Component | Skill File |
|-----------|-----------|
| Full Stack routing | `.claude/skills/autocrud-fullstack/SKILL.md` |
| AutoCRUD Core | `.claude/skills/autocrud-core/SKILL.md` |
| ResourceManager | `.claude/skills/resource-manager/SKILL.md` |
| Schema API | `.claude/skills/schema/SKILL.md` |
| Query Builder | `.claude/skills/query-builder/SKILL.md` |
| Route Templates | `.claude/skills/route-templates/SKILL.md` |
| Storage Factory | `.claude/skills/storage-factory/SKILL.md` |
| Permission | `.claude/skills/permission/SKILL.md` |
| Web Generator | `.claude/skills/web-generator/SKILL.md` |
| Web App | `.claude/skills/web-app/SKILL.md` |
| Docs Maintenance | `.claude/skills/docs-maintenance/SKILL.md` |
