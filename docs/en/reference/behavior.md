# Behavior & lifecycle guarantees

This page documents lifecycle expectations and safe usage rules for `AutoCRUD`.

## Recommended initialization order

1. Create `AutoCRUD` instance (or import global `crud`)
2. `configure()` (optional) — configure defaults for the instance
3. `add_model()` — register all models/schemas
4. `apply()` — generate routes on a `FastAPI` / `APIRouter`
5. Serve requests

## Thread safety & concurrency

`AutoCRUD` maintains mutable registries such as:

- `resource_managers`
- route template list
- relationship metadata collected from `Ref` annotations
- pending create actions

Therefore:

- **Do** call `configure()`, `add_model()`, `add_route_template()`, `create_action()`
  during application startup.
- Avoid calling these after the app starts serving requests, because they mutate global
  structures and can lead to inconsistent behavior.

Concurrency characteristics of request-time operations depend on the selected storage backend
and the underlying `ResourceManager` implementation.

## Calling `configure()` after models exist

`configure()` logs a warning when called after any model is registered. Treat this as
"supported for development, not recommended for production".

## `apply()` side effects

Calling `apply()` will:

- validate `Ref` targets (warn on dangling refs)
- install referential integrity event handlers
- sort and apply route templates for each registered model
- register custom create action routes
- add ref-specific routes (referrers + relationships)
- add global backup/restore routes

## OpenAPI customization

`openapi()` mutates `app.openapi_schema` to inject:

- AutoCRUD-related schemas into `components.schemas`
- ref metadata extensions (`x-ref-*`, `x-ref-revision-*`) on schema properties
- top-level extension for custom create actions (`x-autocrud-custom-create-actions`)

In most cases you don't need to call `openapi()` manually because it is used by `apply()` flows.
