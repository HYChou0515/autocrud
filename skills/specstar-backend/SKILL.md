---
name: specstar-backend
description: Build FastAPI REST APIs with SpecStar — spec-driven CRUD generation with built-in versioning, permissions, search, GraphQL, binary storage, schema migration, and message queue. Use this skill whenever the user works with SpecStar in Python, including defining data models (msgspec.Struct or Pydantic), configuring storage backends (Memory/Disk/S3/PostgreSQL), writing Query Builder (QB) expressions, using ResourceManager methods (create/get/update/delete/search/migrate/switch), setting up Schema migrations, adding route templates, creating custom create/update actions, handling events, processing async jobs with Job[T]/JobContext/DelayRetry, managing relationships with Ref/OnDelete, or building any FastAPI application powered by SpecStar. Also trigger when users ask about generating REST endpoints, building CRUD APIs, auto-generating API routes from models, data versioning or revision history, audit trails, soft delete and restore, file/binary/blob uploads, schema evolution or data migration, background job processing or async tasks, foreign key relationships between resources, or searching/filtering/querying API data — even if they don't explicitly mention SpecStar by name. Trigger on mentions of specstar, spec.configure, spec.add_model, spec.apply, spec.create_action, spec.update_action, Schema, ResourceManager, QB, DependencyProvider, DiskStorageFactory, S3StorageFactory, PostgresStorageFactory, or any SpecStar-specific API. Also trigger on legacy autocrud names (crud.configure, crud.add_model, crud.apply, AutoCRUD) since pre-0.10 code still uses them via the shim.
---

# SpecStar Backend Skill

SpecStar is a **spec-driven backend platform for FastAPI** that generates complete REST APIs with **versioning, permissions, search, binary storage, schema migration, and async job processing** from Python data models. See `references/` for detailed API reference.

> Setting up a new project or registering models? Read `references/setup-gotchas.md` first — it covers the most common import path and naming mistakes.

## Key Decisions

Before diving into the API, here are the choices you'll face and the reasoning behind each:

**Struct vs Pydantic?** Use `msgspec.Struct` (recommended) for performance and native SpecStar compatibility. Use Pydantic `BaseModel` when you need Pydantic validators or are migrating existing Pydantic code — SpecStar converts it internally via `pydantic_to_struct()`.

**Which storage factory?** Pick based on your deployment stage:
- `MemoryStorageFactory` — tests and demos (data lost on restart)
- `DiskStorageFactory` — local dev and small production (SQLite + filesystem)
- `S3StorageFactory` — cloud deployment (SQLite-in-S3 + S3 objects) — requires `s3` extra
- `PostgresStorageFactory` — large-scale production (full PostgreSQL) — requires `postgresql` extra

Different storage and feature backends require installing extra dependencies. See the **Extra Dependencies by Feature** table below for the full mapping.

**Which message queue factory?** Pick based on your infrastructure:
- `SimpleMessageQueueFactory` — in-process queue, no infrastructure needed (default)
- `RabbitMQMessageQueueFactory` — distributed, production-ready — requires `mq` extra
- `CeleryMessageQueueFactory` — distributed via Celery workers — requires `celery` extra

**`update()` vs `modify()`?** `update()` creates a new immutable revision — use it when you want to preserve history (the default for most workflows). `modify()` edits the current revision in-place — use it only for draft content that isn't finalized yet (e.g., a form being composed step by step).

**`draft` vs `stable` status?** `stable` revisions are immutable (you must `update()` to create a new one). `draft` revisions can be `modify()`-ed in place. Set `default_status="draft"` if your workflow involves iterative editing before publishing.

**When to use Schema versioning?** Skip it for early development. Add `Schema(Model, "v1")` when your data structure stabilizes. Add migration steps (`Schema(V2, "v2").step("v1", fn)`) only when you change the model shape and have existing data that needs to migrate.

**`UNSET` vs `None`?** `None` means "this field is explicitly null." `UNSET` means "this field was not provided at all." This distinction matters in PATCH operations — an `UNSET` field is left unchanged, while `None` actively clears the value.

## Quick Start

```python
from msgspec import Struct
from fastapi import FastAPI
from specstar import crud

class User(Struct):
    name: str
    email: str

app = FastAPI()
crud.add_model(User)
crud.apply(app)
# Generates: POST/GET /user, GET/PUT/PATCH/DELETE /user/{id}, plus restore & switch-revision
```

### Full Example (storage + MQ + custom actions)

```python
from fastapi import FastAPI
from msgspec import Struct
from specstar import crud, Schema
from specstar.resource_manager.storage_factory import DiskStorageFactory
from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.crud.route_templates.basic import DependencyProvider
from specstar.crud.route_templates.graphql import GraphQLRouteTemplate
from specstar.crud.route_templates.blob import BlobRouteTemplate
import datetime as dt

app = FastAPI()

crud.configure(
    storage_factory=DiskStorageFactory("./data"),
    message_queue_factory=SimpleMessageQueueFactory(),
    dependency_provider=DependencyProvider(
        get_user=lambda: "admin",
        get_now=lambda: dt.datetime.now(),
    ),
    model_naming="kebab",
)
crud.add_route_template(GraphQLRouteTemplate())
crud.add_route_template(BlobRouteTemplate())

crud.add_model(User, indexed_fields=[("name", str), ("email", str)])
crud.apply(app)
```

## Public API (all from `specstar`)

```python
from specstar import (
    SpecStar, crud, Schema, LoadStats, struct_to_pydantic,
    DisplayName, Unique, Ref, RefRevision, OnDelete, OnDuplicate, RefType,
    IConstraintChecker, IValidator, ValidationError,
    UniqueConstraintError, DuplicateResourceError, RevisionNotMigratedError,
    SearchedResource, ResourceOps,
    BackgroundTaskAccepted, BlobUploadSession, JobRedirectInfo,
    MissingOperationContextError,
)
```

## Model Definition

### msgspec.Struct (recommended)

```python
from msgspec import Struct
from typing import Annotated
from enum import Enum
from specstar import DisplayName, Unique, Ref, OnDelete
from specstar.types import Binary

class Role(Enum):
    ADMIN = "admin"
    USER = "user"

class User(Struct):
    name: Annotated[str, DisplayName()]                              # human label in admin UI
    email: Annotated[str, Unique()]                                  # unique constraint
    role: Role = Role.USER
    age: int = 0
    bio: str | None = None
    team_id: Annotated[str | None, Ref("team", on_delete=OnDelete.set_null)] = None  # FK
    skill_ids: list[Annotated[str, Ref("skill")]] = []              # array of refs
    avatar: Binary | None = None                                     # blob file
    config: dict | None = None                                       # arbitrary JSON
```

### Pydantic BaseModel

```python
from pydantic import BaseModel, field_validator

class User(BaseModel):
    name: Annotated[str, DisplayName()]
    email: Annotated[str, Unique()]
    age: int = 0

    @field_validator("age")
    @classmethod
    def check_age(cls, v):
        if v < 0: raise ValueError("Age must be non-negative")
        return v
```

### Tagged Unions (discriminated)

```python
class ActiveSkill(Struct, tag_field="type", tag="active"):
    mp_cost: int = 0
    cooldown: int = 0

class PassiveSkill(Struct, tag_field="type", tag="passive"):
    buff_pct: int = 0

class Skill(Struct):
    name: str
    detail: ActiveSkill | PassiveSkill  # discriminated union
```

### Field Annotations

| Annotation | Purpose | Example |
|-----------|---------|---------|
| `DisplayName()` | Human-readable label | `Annotated[str, DisplayName()]` |
| `Unique()` | Uniqueness constraint | `Annotated[str, Unique()]` |
| `Ref("resource")` | Foreign key | `Annotated[str, Ref("team")]` |
| `Ref("r", on_delete=OnDelete.cascade)` | Delete child when parent deleted | `Annotated[str, Ref("team", on_delete=OnDelete.cascade)]` |
| `Ref("r", on_delete=OnDelete.set_null)` | Nullify on parent delete | `Annotated[str \| None, Ref("team", on_delete=OnDelete.set_null)]` |
| `Ref("r", ref_type=RefType.revision_id)` | Ref to specific revision | `Annotated[str, Ref("user", ref_type=RefType.revision_id)]` |
| `Binary` | Blob file (stored in blob store) | `avatar: Binary \| None = None` |

## Configuration (`crud.configure`)

```python
crud.configure(
    storage_factory=...,             # MemoryStorageFactory / DiskStorageFactory / S3StorageFactory / PostgresStorageFactory
    message_queue_factory=...,       # SimpleMessageQueueFactory / RabbitMQMessageQueueFactory / CeleryMessageQueueFactory
    dependency_provider=...,         # DependencyProvider(get_user=..., get_now=...)
    permission_checker=...,          # IPermissionChecker implementation
    model_naming="kebab",            # kebab | snake | camel | pascal | same | callable
    encoding="json",                 # json | msgpack
    default_status="stable",         # draft | stable — initial revision status
    default_user="anonymous",        # str or Callable[[], str]
    event_handlers=[...],            # list[IEventHandler]
    route_templates=[...],           # list or dict
    strict_operation_context=False,  # require user/now on every write
)
```

See `references/storage-and-mq.md` for storage factory constructors, per-model overrides, message queue options, and DependencyProvider setup.

## Model Registration (`crud.add_model`)

```python
crud.add_model(
    User,                                 # type or Schema(type, "v1")
    name="user",                          # custom resource name (default: auto from class)
    indexed_fields=[("email", str), ("name", str)],  # tuple format for search optimization
    storage=custom_factory,               # per-model storage override
    permission_checker=custom_checker,    # per-model permission
    event_handlers=[my_handler],          # per-model events
    encoding="msgpack",                   # per-model encoding
    default_status="draft",              # per-model default status
    validator=validate_fn,                # function or IValidator
    job_handler=process_job,              # Job[T] handler (activates MQ)
    constraint_checkers=[...],            # custom constraint logic
)
crud.apply(app)  # generates all routes
crud.apply(app, router=APIRouter(prefix="/v1"))  # mount under prefix
```

Validators can be a function `(data) → None` that raises on invalid input, or an `IValidator` class with a `.validate()` method. See `references/resource-manager.md` for examples.

## ResourceManager API

Get a ResourceManager for programmatic CRUD outside of HTTP routes:

```python
rm = crud.get_resource_manager(User)     # by type
rm = crud.get_resource_manager("user")   # by name

# Context manager sets audit user/time for all operations inside
with rm.using(user="admin", now=dt.datetime.now()):
    info = rm.create(User(name="Alice", email="a@b.com"))     # → RevisionInfo
    resource = rm.get(info.resource_id)                        # → Resource[User]
    rm.update(info.resource_id, User(name="Alice V2", email="a@b.com"))  # new revision
    rm.modify(info.resource_id, User(name="Draft", email="a@b.com"))     # in-place edit
    rm.switch(info.resource_id, info.revision_id)              # switch active revision
    rm.delete(info.resource_id)                                # soft delete
    rm.restore(info.resource_id)                               # undo delete
    metas = rm.search_resources(QB["name"].contains("Ali").sort("-created_at").limit(10))
```

Key methods: `create`, `get`, `update`, `modify`, `patch`, `create_or_update`, `delete`, `restore`, `permanently_delete`, `switch`, `migrate`, `exists`, `get_meta`, `search_resources`, `list_resources`, `count_resources`, `get_blob`, `start_consume`, `dump`. See `references/resource-manager.md` for the full method table with signatures.

## Schema & Migration (see references/query-and-schema.md for details)

```python
from specstar import Schema

crud.add_model(User)                       # no versioning
crud.add_model(Schema(User, "v1"))         # explicit version
Schema(UserV2, "v2").step("v1", fn)        # with migration step
Schema(UserV2, "v2").step("v1", fn, source_type=UserV1)  # typed migration (recommended)
Schema(UserV3, "v3").step("v1", fn1).step("v2", fn2)     # chained: v1→v2→v3
Schema(UserV3, "v3").step("v1", fn1).step("v2", fn2).plus("v1", fn_shortcut)  # BFS shortest
Schema(User, "v1", validator=validate_user)                # with validator

# Typed migration function (recommended)
def migrate_v1_to_v2(old: UserV1) -> UserV2:
    return UserV2(name=old.name, email=old.email, role="user")

# Runtime migration
rm.migrate(resource_id)                          # current revision
rm.migrate(resource_id, revision_id="abc:1")     # specific old revision
```

## Query Builder (QB) (see references/query-and-schema.md for full operator table)

```python
from specstar.query import QB

# Field comparisons — bracket notation + operator overloading
q = QB["name"].eq("Alice")         # or QB["name"] == "Alice"
q = QB["age"].gte(18)              # gte/gt/lte/lt/eq/ne
q = QB["email"].contains("@g")     # also: startswith, endswith
q = QB["role"].in_(["admin", "user"])  # also: is_null, is_not_null, between

# Logical operators
q = (QB["age"].gte(18) & QB["role"].eq("admin"))   # AND
q = (QB["age"].lt(18) | QB["role"].eq("guest"))     # OR
q = ~QB["name"].eq("Bob")                            # NOT

# Metadata fields — QB.created_time(), QB.updated_by(), QB.is_deleted(), QB.resource_id(), etc.
q = QB.created_time().gte(dt.datetime(2024, 1, 1))

# Sorting & pagination
q = QB["level"].gte(1).sort("-level", "+name").limit(10).offset(20)
q = QB["level"].gte(1).page(2, 10)   # page 2, 10 per page

# HTTP: GET /user?qb=QB["age"] > 18
```

## Route Templates (see references/routes-and-actions.md for all templates)

Default: Create, List, Read, Update, Patch, Delete, Restore, SwitchRevision.

```python
from specstar.crud.route_templates.blob import BlobRouteTemplate
from specstar.crud.route_templates.graphql import GraphQLRouteTemplate
from specstar.crud.route_templates.migrate import MigrateRouteTemplate
from specstar.crud.route_templates.delete import PermanentlyDeleteRouteTemplate, BatchDeleteRouteTemplate, BatchRestoreRouteTemplate
from specstar.crud.route_templates.backup import ExportRouteTemplate, ImportRouteTemplate

crud.add_route_template(BlobRouteTemplate())              # blob upload/download
crud.add_route_template(GraphQLRouteTemplate())           # POST /graphql
crud.add_route_template(MigrateRouteTemplate())           # schema migration endpoint
crud.add_route_template(PermanentlyDeleteRouteTemplate()) # hard delete
crud.add_route_template(BatchDeleteRouteTemplate())       # bulk soft delete
```

### Custom Create Actions (see references/routes-and-actions.md for async_mode details)

```python
@crud.create_action("character", label="Generate Random")
async def gen_random():
    return Character(name=f"Hero-{random.randint(1,100)}", level=1)

@crud.create_action("character", path="/{name}/new", async_mode="job", job_name="create-char-job")
async def create_by_name(name: Annotated[str, Ref("equipment")]):
    return Character(name=name, level=1)
# async_mode: None (sync) | "background" (fire-and-forget) | "job" (tracked via MQ)
```

### Custom Update Actions

```python
@crud.update_action("character", label="Level Up")
async def level_up(existing: Character) -> Character:
    return Character(name=existing.name, level=existing.level + 1)

@crud.update_action("character", label="Rename", meta_param="meta")
async def rename(existing: Character, info: RevisionInfo, meta: ResourceMeta):
    existing.name = f"Renamed-{meta.total_revision_count}"
    return existing
```

## Job System (Message Queue) (see references/storage-and-mq.md for details)

```python
from specstar.types import Job, Resource
from specstar.message_queue.context import JobContext
from specstar.message_queue.basic import DelayRetry

class TaskPayload(Struct):
    query: str
class TaskArtifact(Struct):
    result: str
class GameEvent(Job[TaskPayload]):
    pass  # Job model — automatically queued on create()

def process_event(
    event_resource: Resource[GameEvent],
    job_context: JobContext[TaskPayload, TaskArtifact],
):
    payload = event_resource.data.payload
    job_context.info(f"Processing: {payload.query}")

    # Delay retry — re-enqueue after N seconds
    if not_ready():
        raise DelayRetry(delay_seconds=10)

    job_context.set_artifact(TaskArtifact(result="done"))

# Register with handler
crud.add_model(GameEvent, indexed_fields=[("status", str)], job_handler=process_event)
crud.apply(app)
rm = crud.get_resource_manager(GameEvent)
rm.start_consume(block=False)  # background thread
```

## Event Handlers

```python
from specstar.types import IEventHandler

class AuditLogger(IEventHandler):
    async def handle_event(self, context) -> None:
        print(f"[{context.action}] resource={context.resource_name}")

crud.configure(event_handlers=[AuditLogger()])
```

Event phases: `Before*`, `After*`, `OnSuccess*`, `OnFailure*` for Create, Get, Update, Modify, Patch, Delete, Restore, PermanentlyDelete, Switch, Migrate, SearchResources — 64 total contexts.

## Backup & Restore

```python
import io
from specstar import OnDuplicate, LoadStats

# Export all data to .acbak binary stream
buf = io.BytesIO()
crud.dump(buf)

# Import data
buf.seek(0)
stats: dict[str, LoadStats] = crud.load(buf, on_duplicate=OnDuplicate.overwrite)
# OnDuplicate: overwrite | skip | raise_error
```

## Relationships (Ref & OnDelete)

```python
from specstar import Ref, OnDelete, RefType

class Guild(Struct):
    name: str

class Character(Struct):
    name: str
    guild_id: Annotated[str, Ref("guild", on_delete=OnDelete.cascade)]          # delete char when guild deleted
    mentor_id: Annotated[str | None, Ref("character", on_delete=OnDelete.set_null)] = None
    skill_ids: list[Annotated[str, Ref("skill")]] = []                          # dangling (default)
    pet_rev: Annotated[str, Ref("pet", ref_type=RefType.revision_id)] = ""      # ref to specific revision

crud.add_model(Guild)
crud.add_model(Character)  # SpecStar auto-installs referential integrity handlers
```

## Extra Dependencies by Feature

Different storage factories, message queue backends, and optional features require installing the corresponding extra dependency:

| Feature / Factory | Extra | Install Command |
|---|---|---|
| `MemoryStorageFactory` | *(none)* | `pip install specstar` |
| `DiskStorageFactory` | *(none)* | `pip install specstar` |
| `S3StorageFactory` | `s3` | `pip install "specstar[s3]"` |
| `PostgresStorageFactory` | `postgresql` | `pip install "specstar[postgresql]"` |
| `RabbitMQMessageQueueFactory` | `mq` | `pip install "specstar[mq]"` |
| `CeleryMessageQueueFactory` | `celery` | `pip install "specstar[celery]"` |
| `GraphQLRouteTemplate` | `graphql` | `pip install "specstar[graphql]"` |
| `BlobRouteTemplate` (MIME detection) | `magic` | `pip install "specstar[magic]"` |
| Redis MetaStore | `redis` | `pip install "specstar[redis]"` |
| CLI tools | `cli` | `pip install "specstar[cli]"` |

Combine multiple extras: `pip install "specstar[s3,postgresql,mq]"`

## Install

```bash
pip install specstar              # core only
pip install "specstar[all]"       # all extras
# Individual extras: s3, postgresql, redis, mq, celery, graphql, cli, magic
```

## Key Conventions

- **Versioning**: Every `update()` creates a new immutable revision (like Git commits), giving you full edit history and the ability to roll back. `modify()` edits a draft in-place — only use it for iterative authoring before publishing
- **UNSET pattern**: `msgspec.UNSET` / `UnsetType` distinguishes "not provided" from `None` — essential for PATCH semantics where omitted fields should remain unchanged while `None` actively clears a value
- **Soft delete**: `delete()` marks `is_deleted=True` (recoverable, data preserved); `restore()` reverses it; `permanently_delete()` removes all data and revisions irreversibly — use the soft approach by default so users can recover from mistakes
- **Data coercion**: Accepts `dict`, `Struct`, or `BaseModel` as input — internally always converts to `Struct` for consistent serialization. Never return Pydantic instances from ResourceManager
- **Model naming**: `model_naming="kebab"` → `UserProfile` becomes `/user-profile` in URLs. Choose the naming convention that matches your frontend's expectations
- **Indexed fields**: Use tuple format `[("field", type)]` — indexed fields become searchable via QB and appear as filter options in the admin UI. Index the fields users will query most often
- **Return types**: `create/update/modify/patch` → `RevisionInfo` (contains `resource_id` + `revision_id`); `delete/restore/switch/migrate` → `ResourceMeta` (full metadata); `get` → `Resource[T]` (metadata + typed data)
