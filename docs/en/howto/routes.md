# Routes generation (FastAPI)

AutoCRUD generates API endpoints by applying **route templates** to each registered resource
when you call `apply(router)`.

> Important: the final set of endpoints depends on:
> - `model_naming` / `add_model(name=...)`
> - `route_templates` (default or customized)
> - whether you use `create_action()` / ref routes / backup routes

## Minimal usage

```python
from fastapi import FastAPI
from autocrud import crud

app = FastAPI()

crud.add_model(User)
crud.apply(app)
```

## Resource name → base path

A model is registered with a resource name:

* `add_model(User)` → name inferred from model class + `model_naming`
* `add_model(User, name="people")` → override path base to `/people`

## Default templates (typical endpoints)

When `route_templates` is `None` (default behavior) or a configuration dict, AutoCRUD installs
a default set of templates (create/list/read/update/patch/delete/restore/export/import, etc).

For a resource named `users`, you typically get endpoints like:

* `POST /users` — create
* `GET /users/...` — list variants (depending on templates, may include data/meta/full/revision views)
* `GET /users/{id}/...` — read variants (depending on templates)
* `PUT /users/{id}` — replace
* `PATCH /users/{id}` — RFC6902 JSON Patch (if Patch template is enabled)
* `DELETE /users/{id}` — soft delete (if Delete template is enabled)
* `POST /users/{id}/restore` — restore (if Restore template is enabled)
* Revision-related endpoints (switch / list / info) depending on templates

### Why the endpoints are not listed exhaustively here

AutoCRUD supports customizing templates and adding custom routes. If you need an authoritative list,
use your generated OpenAPI docs (Swagger UI / ReDoc) after calling `apply()`.

## Custom route templates

### Configure default templates (dict form)

You can pass a dict `{TemplateClass: kwargs}` to configure default templates:

```python
from autocrud import AutoCRUD
from autocrud.crud.route_templates import ListRouteTemplate

autocrud = AutoCRUD(route_templates={
    ListRouteTemplate: {"dependency_provider": my_provider},
})
```

### Provide a full template list

```python
autocrud = AutoCRUD(route_templates=[
    CreateRouteTemplate(...),
    ListRouteTemplate(...),
])
```

### Add templates incrementally

```python
autocrud.add_route_template(MyCustomTemplate())
```

Templates should be added before `apply()` for predictable behavior.

## Custom create actions

Use `create_action()` to add additional create endpoints for a resource:

```python
from msgspec import Struct
from fastapi import Body
from autocrud import crud

class ImportFromUrl(Struct):
    url: str

@crud.create_action("article", label="Import from URL")
async def import_from_url(body: ImportFromUrl = Body(...)):
    content = await fetch_and_parse(body.url)
    return Article(content=content)  # returning a resource triggers auto-create
```

`create_action()` is lazy: it stores metadata and routes are created at `apply()` time.

## Relationships (refs)

If you use `Ref(...)` fields, AutoCRUD may install relationship-related routes and behaviors.
See: `docs/howto/relationships.md` and `docs/concepts/refs.md`.
