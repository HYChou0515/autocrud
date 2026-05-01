# Route Templates & Custom Actions — Detailed Reference

## Route Generation Flow

```python
crud.add_model(User)       # register model
crud.apply(app)            # generate all routes
crud.apply(app, router=APIRouter(prefix="/v1"))  # mount under prefix
```

`apply()` validates Ref targets, installs referential integrity handlers, sorts and applies route templates, registers custom actions, adds ref-specific routes, and adds global backup/restore routes.

## Default Route Templates

These are automatically enabled for every registered model:

| Template | Method | Path | Purpose |
|----------|--------|------|---------|
| `CreateRouteTemplate` | `POST` | `/{resource}` | Create resource |
| `ListRouteTemplate` | `GET` | `/{resource}/data`, `/meta`, `/full`, etc. | Search/list with pagination + QB |
| `ReadRouteTemplate` | `GET` | `/{resource}/{id}?returns=data,meta,revision_info` | Get single resource |
| `UpdateRouteTemplate` | `PUT` | `/{resource}/{id}?mode=update\|modify` | Full replace (new revision or in-place) |
| `PatchRouteTemplate` | `PATCH` | `/{resource}/{id}` | JSON Merge Patch (RFC 7386) |
| `DeleteRouteTemplate` | `DELETE` | `/{resource}/{id}` | Soft delete |
| `RestoreRouteTemplate` | `POST` | `/{resource}/{id}/restore` | Restore soft-deleted |
| `SwitchRouteTemplate` | `POST` | `/{resource}/{id}/switch-revision` | Change active revision |

## Additional Route Templates

Add these explicitly for extra endpoints:

```python
from specstar.crud.route_templates.blob import BlobRouteTemplate
from specstar.crud.route_templates.graphql import GraphQLRouteTemplate
from specstar.crud.route_templates.migrate import MigrateRouteTemplate
from specstar.crud.route_templates.delete import (
    PermanentlyDeleteRouteTemplate,
    BatchDeleteRouteTemplate,
    BatchRestoreRouteTemplate,
)
from specstar.crud.route_templates.backup import ExportRouteTemplate, ImportRouteTemplate
from specstar.crud.route_templates.rerun import RerunRouteTemplate
```

| Template | Method | Path | Purpose |
|----------|--------|------|---------|
| `BlobRouteTemplate` | `POST/GET` | `/{resource}/{id}/blobs/{file_id}` | Upload/download binary files |
| `GraphQLRouteTemplate` | `POST` | `/graphql` | GraphQL endpoint for all models |
| `MigrateRouteTemplate` | `POST` | `/{resource}/{id}/migrate` | Schema migration endpoint |
| `PermanentlyDeleteRouteTemplate` | `DELETE` | `/{resource}/{id}/permanent` | Hard delete (irreversible) |
| `BatchDeleteRouteTemplate` | `DELETE` | `/{resource}?field=value` | Bulk soft delete |
| `BatchRestoreRouteTemplate` | `POST` | `/{resource}/restore?field=value` | Bulk restore |
| `ExportRouteTemplate` | `GET` | `/{resource}/backup` | Export model data |
| `ImportRouteTemplate` | `POST` | `/{resource}/backup/import` | Import model data |
| `RerunRouteTemplate` | `POST` | `/{resource}/{id}/rerun` | Re-enqueue failed job |

### Adding Templates

```python
# Method 1: add_route_template (before apply)
crud.add_route_template(BlobRouteTemplate())
crud.add_route_template(GraphQLRouteTemplate())

# Method 2: configure with list
crud.configure(route_templates=[
    BlobRouteTemplate(),
    PermanentlyDeleteRouteTemplate(),
])

# Method 3: configure with dict (customize default templates)
from specstar.crud.route_templates import ListRouteTemplate
crud.configure(route_templates={
    ListRouteTemplate: {"dependency_provider": my_provider},
})
```

## Custom Create Actions

Decorator to register additional create endpoints for a resource:

```python
@crud.create_action(
    resource_name: str,          # which resource (by name)
    *,
    path: str | None = None,     # custom URL path (default: auto-derived from function name)
    label: str | None = None,    # human-readable label (shown in admin UI)
    async_mode: Literal["job", "background"] | None = None,  # execution mode
    job_name: str | None = None, # custom job resource name (for async_mode="job")
)
```

### Sync Create (default)

```python
@crud.create_action("character", label="Generate Random")
async def gen_random():
    return Character(name=f"Hero-{random.randint(1,100)}", level=1)
# → POST /character/gen-random
```

### Background Create (fire-and-forget)

```python
@crud.create_action("character", label="Slow Generate", async_mode="background")
async def slow_gen():
    time.sleep(5)  # long operation
    return Character(name="Background Hero", level=1)
# Returns immediately, creation happens in background thread
```

### Job Create (tracked via MQ)

```python
@crud.create_action("character", label="Job Create", async_mode="job", job_name="create-char-job")
async def job_create(name: Annotated[str, Ref("equipment")]):
    time.sleep(100)
    return Character(name=name, level=1)
# Creates a tracked job resource; consumer processes it asynchronously
# Start consumer: rm.start_consume(block=False, custom_creation=["create-char-job"])
```

### Custom Path with Parameters

```python
@crud.create_action("character", path="/{name}/new", async_mode="job")
async def create_by_name(name: str):
    return Character(name=name, level=1)
# → POST /character/{name}/new
```

### Complex Parameters

```python
from fastapi import Body, UploadFile
from specstar import struct_to_pydantic, Ref

@crud.create_action("character", label="Complex Create", async_mode="job")
async def complex_create(
    x: int | str,
    name: Annotated[str, Body(embed=True), Ref("equipment")],
    z: UploadFile,
    skill: struct_to_pydantic(Skill),  # converts Struct to Pydantic for FastAPI validation
):
    return Character(name=f"{name} ({x})", level=1)
```

## Custom Update Actions

Decorator to register additional update endpoints for an existing resource:

```python
@crud.update_action(
    resource_name: str,
    *,
    path: str | None = None,
    label: str | None = None,
    mode: Literal["update", "modify"] = "update",  # update=new revision, modify=in-place
    existing_param: str = "existing",    # parameter name for current resource data
    info_param: str = "info",            # parameter name for RevisionInfo injection
    meta_param: str = "meta",            # parameter name for ResourceMeta injection
    async_mode: Literal["job", "background"] | None = None,
    job_name: str | None = None,
)
```

### Basic Update Action

```python
@crud.update_action("character", label="Level Up")
async def level_up(existing: Character) -> Character:
    return Character(
        name=existing.name,
        level=existing.level + 1,
    )
# → POST /character/{resource_id}/level-up
# Creates new revision with updated data
```

### With RevisionInfo and ResourceMeta

```python
@crud.update_action("character", label="Rename", meta_param="xx")
async def rename(existing: Character, info: RevisionInfo, xx: ResourceMeta):
    existing.name = f"Renamed-{xx.total_revision_count}-{info.updated_time}"
    return existing
# Injects current data + revision info + resource metadata
```

### Modify Mode (in-place draft edit)

```python
@crud.update_action("character", label="Quick Fix", mode="modify")
async def quick_fix(existing: Character) -> Character:
    existing.name = existing.name.strip()
    return existing
# Edits current revision in-place (no new revision)
```

### Background Update

```python
@crud.update_action("character", label="Slow Update", async_mode="background")
async def slow_update(existing: Character) -> Character:
    time.sleep(5)
    existing.name = f"Updated-{time.time()}"
    return existing
# Returns immediately, update happens in background
```

### Return None = No Update

```python
@crud.update_action("character", label="Conditional Update")
async def conditional(existing: Character) -> Character | None:
    if existing.level >= 100:
        return None  # no update performed
    return Character(name=existing.name, level=existing.level + 1)
```

## Starting Async Consumers

```python
crud.apply(app)

# Start MQ consumer for Job models
rm = crud.get_resource_manager(GameEvent)
rm.start_consume(block=False)

# Start consumer for custom async actions
rm = crud.get_resource_manager(Character)
rm.start_consume(
    block=False,
    custom_creation="all",     # consume all async create-action jobs
    custom_update="all",       # consume all async update-action jobs
)
# Or specific ones:
rm.start_consume(custom_creation=["create-char-job"])
```

## Global Backup & Restore Routes

`apply()` automatically adds global routes:

- `GET /backup` — export all resources as `.acbak` archive
- `POST /backup/import` — import from `.acbak` archive

```python
# Programmatic backup/restore
import io
from specstar import OnDuplicate

buf = io.BytesIO()
crud.dump(buf)

buf.seek(0)
stats = crud.load(buf, on_duplicate=OnDuplicate.overwrite)
# stats: {"user": LoadStats(loaded=10, skipped=0, total=10), ...}
```

## OpenAPI Customization

`apply()` automatically customizes OpenAPI schema with:

- `x-ref-*` / `x-ref-revision-*` extensions on schema properties
- `x-specstar-custom-create-actions` for custom create endpoints
- `x-specstar-custom-update-actions` for custom update endpoints
- SpecStar-related schemas in `components.schemas`

## Ref Routes

For models with `Ref()` annotations, `apply()` also generates:

- **Referrer routes**: Find resources that reference a given resource
- **Relationship routes**: Navigate relationships between resources

These are derived automatically from the `Ref()` annotations in your models.
