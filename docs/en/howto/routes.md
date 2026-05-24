# Routes generation (FastAPI)

SpecStar generates API endpoints by applying **route templates** to each registered resource
when you call `apply()`.

> Important: the final set of endpoints depends on:
> - `model_naming` / `add_model(name=...)`
> - `route_templates` (default or customized)
> - whether you use `create_action()` / `update_action()` / ref routes / backup routes

## Minimal usage

```python
from fastapi import FastAPI
from specstar import spec

app = FastAPI()

spec.add_model(User)
spec.apply(app)  # routes + OpenAPI schema generated automatically
```

## Using a sub-router

```python
from fastapi import APIRouter, FastAPI
from specstar import spec

app = FastAPI()
router = APIRouter(prefix="/api/v1")

spec.add_model(User)
spec.apply(app, router=router)  # auto include_router + auto openapi
```

When `app` is a `FastAPI` instance, `apply()` automatically calls `openapi(app)` to
generate the OpenAPI schema. When `router` is provided, `app.include_router(router)`
is called before OpenAPI generation (controlled by `auto_include`, default `True`).

## Resource name → base path

A model is registered with a resource name:

* `add_model(User)` → name inferred from model class + `model_naming`
* `add_model(User, name="people")` → override path base to `/people`

### `model_naming` reference

The `model_naming` setting on `SpecStar` / `spec.configure()` controls how
**class names** become **URL segments**. The default is `"kebab"` — lowercase
words joined by hyphens.

| `model_naming` | `User`     | `BlogPost`   | `URLPath`    | `XMLNode`   |
|----------------|------------|--------------|--------------|-------------|
| `"kebab"` *(default)* | `/user`    | `/blog-post` | `/url-path` | `/xml-node` |
| `"snake"`      | `/user`    | `/blog_post` | `/url_path` | `/xml_node` |
| `"camel"`      | `/user`    | `/blogPost`  | `/urlPath`   | `/xmlNode`  |
| `"pascal"`     | `/User`    | `/BlogPost`  | `/UrlPath`   | `/XmlNode`  |
| `"same"`       | `/User`    | `/BlogPost`  | `/URLPath`   | `/XMLNode`  |
| callable       | `model_naming=lambda cls: cls.__name__.lower() + "s"` → `/users` |

Names are **singular by default** (no automatic pluralisation). Pass
`name=` to `add_model` to override a single model, or supply a callable to
`model_naming` for project-wide custom rules (including plurals).

## Default templates (typical endpoints)

When `route_templates` is `None` (default behavior) or a configuration dict, SpecStar installs
a default set of templates (create/list/read/update/patch/delete/restore/export/import, etc).

For a `User` model (path segment follows `model_naming`, default
**kebab-case singular** — e.g. `User → /user`, `BlogPost → /blog-post`),
you typically get endpoints like:

* `POST /user` — create
* `GET /user` — list (variants under `?returns=…`; see [API conventions](/specstar/howto/api-conventions))
* `GET /user/{resource_id}` — read (variants under `?returns=…`)
* `PUT /user/{resource_id}` — **full replace** (not upsert; missing id → `404`)
* `PATCH /user/{resource_id}` — **RFC 6902 JSON Patch** body (an array of ops,
  not a partial object). Posting a partial object returns
  `400 "Document is expected to be sequence of operations"`.
* `DELETE /user/{resource_id}` — soft delete (if Delete template is enabled)
* `POST /user/{resource_id}/restore` — restore (if Restore template is enabled)
* Revision-related endpoints (switch / list / info) depending on templates

> Path params are always named `resource_id` (not `id`).

### Why the endpoints are not listed exhaustively here

SpecStar supports customizing templates and adding custom routes. If you need an authoritative list,
use your generated OpenAPI docs (Swagger UI / ReDoc) after calling `apply()`.

## Custom route templates

### Configure default templates (dict form)

You can pass a dict `{TemplateClass: kwargs}` to configure default templates:

```python
from specstar import SpecStar
from specstar.crud.route_templates import ListRouteTemplate

specstar = SpecStar(route_templates={
    ListRouteTemplate: {"dependency_provider": my_provider},
})
```

### Provide a full template list

```python
specstar = SpecStar(route_templates=[
    CreateRouteTemplate(...),
    ListRouteTemplate(...),
])
```

### Add templates incrementally

```python
specstar.add_route_template(MyCustomTemplate())
```

Templates should be added before `apply()` for predictable behavior.

## Custom create actions

Use `create_action()` to add additional create endpoints for a resource:

```python
from msgspec import Struct
from fastapi import Body
from specstar import spec

class ImportFromUrl(Struct):
    url: str

@spec.create_action("article", label="Import from URL")
async def import_from_url(body: ImportFromUrl = Body(...)):
    content = await fetch_and_parse(body.url)
    return Article(content=content)  # returning a resource triggers auto-create
```

`create_action()` is lazy: it stores metadata and routes are created at `apply()` time.

## Custom update actions

Use `update_action()` to add custom update endpoints for an existing resource.
The handler automatically receives the current resource data (injected by parameter name),
and can optionally receive `RevisionInfo` and `ResourceMeta`.

```python
from msgspec import Struct
from fastapi import Body
from specstar import spec

class LevelUpInput(Struct):
    levels: int = 1

@spec.update_action("character", label="Level Up")
def level_up(existing: Character, body: LevelUpInput = Body(...)) -> Character:
    return Character(
        name=existing.name,
        level=existing.level + body.levels,
    )
```

Key differences from `create_action()`:

* Route: `POST /{resource}/{resource_id}/{action_path}` (includes `resource_id`)
* The existing resource is auto-fetched via `rm.get(resource_id)` and injected into the
  parameter named by `existing_param` (default `"existing"`)
* `mode="update"` (default) creates a new revision; `mode="modify"` edits the draft in-place
* If the handler returns `None`, no update is performed

`update_action()` is lazy — routes are registered at `apply()` time.

### Async update actions

Both `create_action()` and `update_action()` support an `async_mode` parameter for
long-running operations:

* **`async_mode="job"`** — creates a Job resource in the message queue system.
  The endpoint returns HTTP 202 with a `JobRedirectInfo`. The actual update runs
  in the MQ consumer, which lazy-fetches the existing resource before calling your handler.

* **`async_mode="background"`** — schedules the handler via FastAPI `BackgroundTasks`.
  The endpoint returns HTTP 202 immediately. No Job model is created (fire-and-forget).

```python
from msgspec import Struct
from fastapi import Body
from specstar import spec


class TrainInput(Struct):
    hours: int = 1


# Job mode — creates a trackable Job resource
@spec.update_action("character", label="Train", async_mode="job")
def train(existing: Character, body: TrainInput = Body(...)) -> Character:
    import time
    time.sleep(body.hours * 10)  # long-running training
    return Character(name=existing.name, level=existing.level + body.hours)


# Background mode — fire-and-forget
@spec.update_action("character", label="Background Heal", async_mode="background")
def bg_heal(existing: Character) -> Character:
    import time
    time.sleep(5)
    return Character(name=existing.name, level=existing.level + 1)
```

Key points:

* Job mode payloads automatically include `resource_id` — the existing resource is
  lazy-fetched at job execution time (not at endpoint time).
* Both `mode="update"` (new revision) and `mode="modify"` (in-place) work with async modes.
* Use `job_name` to override the auto-generated Job resource name.
* If the handler returns `None`, no update is performed.

## Relationships (refs)

If you use `Ref(...)` fields, SpecStar may install relationship-related routes and behaviors.

See also:

- [Relationships](/specstar/howto/relationships)
- [Behavior Reference](/specstar/concepts/refs)

## Common follow-ups

After your routes are generated, the next questions are usually:

- how to validate writes reliably → [Validation](/specstar/concepts/validation)
- how to filter and search results → [Query Builder](/specstar/howto/query-builder)
- what to check when something behaves unexpectedly → [Troubleshooting](/specstar/howto/troubleshooting)
