---
name: autocrud-backend
description: Build FastAPI REST APIs with AutoCRUD — model-driven CRUD generation with built-in versioning, permissions, search, GraphQL, binary storage, schema migration, and message queue. Use this skill whenever the user works with AutoCRUD in Python, including defining data models (msgspec.Struct or Pydantic), configuring storage backends (Memory/Disk/S3/PostgreSQL), writing Query Builder (QB) expressions, using ResourceManager methods (create/get/update/delete/search/migrate/switch), setting up Schema migrations, adding route templates, creating custom create/update actions, handling events, processing async jobs with Job[T]/JobContext/DelayRetry, managing relationships with Ref/OnDelete, or building any FastAPI application powered by AutoCRUD. Trigger on mentions of autocrud, crud.configure, crud.add_model, crud.apply, crud.create_action, crud.update_action, Schema, ResourceManager, QB, DependencyProvider, DiskStorageFactory, S3StorageFactory, PostgresStorageFactory, or any AutoCRUD-specific API.
---

# AutoCRUD Backend Skill

AutoCRUD is a **model-driven FastAPI framework** that generates complete REST APIs with **versioning, permissions, search, binary storage, schema migration, and async job processing** from Python data models. See `references/` for detailed API reference.

## Quick Start

```python
from msgspec import Struct
from fastapi import FastAPI
from autocrud import crud

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
from autocrud import crud, Schema
from autocrud.resource_manager.storage_factory import DiskStorageFactory
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.crud.route_templates.basic import DependencyProvider
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.crud.route_templates.blob import BlobRouteTemplate
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

## Public API (all from `autocrud`)

```python
from autocrud import (
    AutoCRUD, crud, Schema, LoadStats, struct_to_pydantic,
    DisplayName, Unique, Ref, RefRevision, OnDelete, OnDuplicate, RefType,
    IConstraintChecker, IValidator, ValidationError,
    UniqueConstraintError, DuplicateResourceError, RevisionNotMigratedError,
    SearchedResource, ResourceOps,
)
```

## Model Definition

### msgspec.Struct (recommended)

```python
from msgspec import Struct
from typing import Annotated
from enum import Enum
from autocrud import DisplayName, Unique, Ref, OnDelete
from autocrud.types import Binary

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

### Storage Factories (see references/storage-and-mq.md for full options)

```python
from autocrud.resource_manager.storage_factory import (
    MemoryStorageFactory,     # In-memory (testing/demos, data lost on restart)
    DiskStorageFactory,       # SQLite meta + filesystem data (dev/small prod)
    S3StorageFactory,         # SQLite-in-S3 meta + S3 data (cloud)
    PostgresStorageFactory,   # PostgreSQL meta + PostgreSQL data (large-scale)
)

crud.configure(storage_factory=MemoryStorageFactory())          # testing
crud.configure(storage_factory=DiskStorageFactory("./data"))    # local dev
crud.configure(storage_factory=S3StorageFactory(bucket="b", endpoint_url="http://localhost:9000"))  # cloud
crud.configure(storage_factory=PostgresStorageFactory(connection_string="postgresql://..."))        # production

# Per-model override
crud.add_model(User)  # uses global storage
crud.add_model(Image, storage=S3StorageFactory(bucket="images"))  # S3 for images
```

### Message Queue & DependencyProvider

```python
from autocrud.message_queue.simple import SimpleMessageQueueFactory        # in-process
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueueFactory    # distributed
from autocrud.message_queue.celery_queue import CeleryMessageQueueFactory  # Celery workers
from autocrud.crud.route_templates.basic import DependencyProvider

crud.configure(message_queue_factory=SimpleMessageQueueFactory())  # or RabbitMQ / Celery
crud.configure(dependency_provider=DependencyProvider(
    get_user=lambda: "admin", get_now=lambda: dt.datetime.now(),
))
```

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

### Validators

```python
# Function-based
def validate_user(user: User) -> None:
    if user.age < 0:
        raise ValueError("Age cannot be negative")

crud.add_model(Schema(User, "v1", validator=validate_user))

# Class-based (IValidator protocol)
class UserValidator:
    def validate(self, data: User) -> None:
        if not data.email:
            raise ValueError("Email required")

crud.add_model(Schema(User, "v1", validator=UserValidator()))
```

## ResourceManager API

Get a ResourceManager to perform CRUD operations programmatically:

```python
rm = crud.get_resource_manager(User)     # by type
rm = crud.get_resource_manager("user")   # by name
```

### Context for Write Operations

```python
# Context manager — sets audit user/time for all operations inside
with rm.using(user="admin", now=dt.datetime.now()):
    info = rm.create(User(name="Alice", email="a@b.com"))
    rm.update(info.resource_id, User(name="Alice Updated", email="a@b.com"))

# Or pass user/now per-call
info = rm.create(data, user="admin", now=dt.datetime.now())
```

### Core Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `create` | `(data, *, status, user, now, resource_id) → RevisionInfo` | Create new resource |
| `get` | `(resource_id, *, revision_id) → Resource[T]` | Get resource (latest or specific revision) |
| `update` | `(resource_id, data, *, status, user, now) → RevisionInfo` | Create new revision |
| `modify` | `(resource_id, data, status, *, user, now) → RevisionInfo` | Edit current revision in-place (draft) |
| `patch` | `(resource_id, patch_data, *, user, now) → RevisionInfo` | RFC 6902 JSON Patch |
| `create_or_update` | `(resource_id, data, *) → RevisionInfo` | Upsert |
| `delete` | `(resource_id, *, user, now) → ResourceMeta` | Soft delete |
| `restore` | `(resource_id, *, user, now) → ResourceMeta` | Restore soft-deleted |
| `permanently_delete` | `(resource_id, *, user, now) → ResourceMeta` | Hard delete all revisions |
| `switch` | `(resource_id, revision_id, *, user, now) → ResourceMeta` | Change active revision |
| `migrate` | `(resource_id, *, revision_id) → ResourceMeta` | Migrate to latest schema |
| `exists` | `(resource_id) → bool` | Check existence |
| `get_meta` | `(resource_id) → ResourceMeta` | Get metadata only |
| `get_revision_info` | `(resource_id, revision_id) → RevisionInfo` | Get revision metadata |
| `list_revisions` | `(resource_id) → list[str]` | List all revision IDs |
| `search_resources` | `(query) → list[ResourceMeta]` | Search → metadata list |
| `list_resources` | `(query, *, returns, partial) → list[SearchedResource]` | Search → full data |
| `count_resources` | `(query) → int` | Count matching resources |
| `get_blob` | `(file_id) → Binary` | Get binary blob by ID |
| `start_consume` | `(*, block, custom_creation, custom_update)` | Start MQ consumer |
| `dump` | `(query) → Generator` | Export records |

### Usage Example (see references/resource-manager.md for complete API)

```python
rm = crud.get_resource_manager(User)
with rm.using("admin", dt.datetime.now()):
    info = rm.create(User(name="Alice", email="a@b.com"))     # → RevisionInfo
    resource = rm.get(info.resource_id)                        # → Resource[User]
    rm.update(info.resource_id, User(name="Alice V2", email="a@b.com"))  # new revision
    rm.modify(info.resource_id, User(name="Draft", email="a@b.com"))     # in-place edit
    rm.switch(info.resource_id, info.revision_id)              # switch back to r1
    rm.delete(info.resource_id)                                # soft delete
    rm.restore(info.resource_id)                               # restore
    metas = rm.search_resources(QB["name"].contains("Ali").sort("-created_at").limit(10))
    results = rm.list_resources(QB["name"].contains("Ali").limit(10))  # full data
```

## Schema & Migration (see references/query-and-schema.md for details)

```python
from autocrud import Schema

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

# Switch to unmigrated revision
from autocrud import RevisionNotMigratedError
try:
    rm.switch(resource_id, old_revision_id)
except RevisionNotMigratedError:
    rm.migrate(resource_id, revision_id=old_revision_id)
    rm.switch(resource_id, old_revision_id)
```

## Query Builder (QB) (see references/query-and-schema.md for full operator table)

```python
from autocrud.query import QB

# Field comparisons — bracket notation + operator overloading
q = QB["name"].eq("Alice")         # or QB["name"] == "Alice"
q = QB["age"].gte(18)              # gte/gt/lte/lt/eq/ne
q = QB["email"].contains("@g")     # also: startswith, endswith
q = QB["role"].in_(["admin", "user"])  # also: is_null, is_not_null, between

# Logical operators
q = (QB["age"].gte(18) & QB["role"].eq("admin"))   # AND
q = (QB["age"].lt(18) | QB["role"].eq("guest"))     # OR
q = ~QB["name"].eq("Bob")                            # NOT
q = QB["level"].gte(1).filter(QB["name"].contains("A")).exclude(QB["role"].eq("banned"))

# Metadata fields — QB.created_time(), QB.updated_by(), QB.is_deleted(), QB.resource_id(), etc.
q = QB.created_time().gte(dt.datetime(2024, 1, 1))

# Sorting & pagination
q = QB["level"].gte(1).sort("-level", "+name").limit(10).offset(20)
q = QB["level"].gte(1).page(2, 10)   # page 2, 10 per page
q = QB["level"].gte(1).first()        # limit(1) shorthand

# Helpers
q = QB.all(QB["age"].gte(18), QB["role"].eq("admin"))  # AND group
q = QB.any(QB["status"].eq("active"), QB["status"].eq("trial"))  # OR group

# HTTP: GET /user?qb=QB["age"] > 18
```

## Route Templates (see references/routes-and-actions.md for all templates)

Default: Create, List, Read, Update, Patch, Delete, Restore, SwitchRevision.

```python
from autocrud.crud.route_templates.blob import BlobRouteTemplate
from autocrud.crud.route_templates.graphql import GraphQLRouteTemplate
from autocrud.crud.route_templates.migrate import MigrateRouteTemplate
from autocrud.crud.route_templates.delete import PermanentlyDeleteRouteTemplate, BatchDeleteRouteTemplate, BatchRestoreRouteTemplate
from autocrud.crud.route_templates.backup import ExportRouteTemplate, ImportRouteTemplate

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
from autocrud.types import Job, Resource, JobContext, DelayRetry

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
rm.start_consume(block=False)  # background thread; also: custom_creation="all", custom_update="all"
```

## Event Handlers

```python
from autocrud.types import IEventHandler

class AuditLogger(IEventHandler):
    async def handle_event(self, context) -> None:
        print(f"[{context.action}] resource={context.resource_name}")

crud.configure(event_handlers=[AuditLogger()])
```

Event phases: `Before*`, `After*`, `OnSuccess*`, `OnFailure*` for Create, Get, Update, Modify, Patch, Delete, Restore, PermanentlyDelete, Switch, Migrate, SearchResources — 64 total contexts.

## Backup & Restore

```python
import io
from autocrud import OnDuplicate, LoadStats

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
from autocrud import Ref, OnDelete, RefType

class Guild(Struct):
    name: str

class Character(Struct):
    name: str
    guild_id: Annotated[str, Ref("guild", on_delete=OnDelete.cascade)]          # delete char when guild deleted
    mentor_id: Annotated[str | None, Ref("character", on_delete=OnDelete.set_null)] = None
    skill_ids: list[Annotated[str, Ref("skill")]] = []                          # dangling (default)
    pet_rev: Annotated[str, Ref("pet", ref_type=RefType.revision_id)] = ""      # ref to specific revision

crud.add_model(Guild)
crud.add_model(Character)  # AutoCRUD auto-installs referential integrity handlers
```

## Install

```bash
pip install autocrud              # core only
pip install "autocrud[all]"       # all extras
# Individual extras: s3, postgresql, redis, mq, celery, graphql, cli
```

## Key Conventions

- **Versioning**: Every `update()` creates a new immutable revision; `modify()` edits draft in-place
- **UNSET pattern**: `msgspec.UNSET` / `UnsetType` distinguishes "not provided" from `None`
- **Soft delete**: `delete()` sets `is_deleted=True`; `restore()` reverses; `permanently_delete()` removes all data
- **Data coercion**: Accepts `dict`, `Struct`, or `BaseModel` — internally always `Struct`
- **Model naming**: `model_naming="kebab"` → `UserProfile` becomes `/user-profile` in URLs
- **Indexed fields**: Use tuple format `[("field", type)]` for `indexed_fields` parameter
- **Return types**: `create/update/modify/patch` → `RevisionInfo`; `delete/restore/switch/migrate` → `ResourceMeta`; `get` → `Resource[T]`
