# Behavior & initialization guarantees

This page documents safe startup and runtime usage rules for `SpecStar`.

> This page is about initialization, configuration timing, and runtime mutation safety.
> For data evolution and revision history semantics, see [Resource lifecycle](/specstar/concepts/resource-lifecycle).

## Recommended initialization order

1. Create `SpecStar` instance (or import global `spec`)
2. `configure()` (optional) — configure defaults for the instance
3. `add_model()` — register all models/schemas
4. `apply()` — generate routes on a `FastAPI` / `APIRouter`
5. Serve requests

## Thread safety & concurrency

`SpecStar` maintains mutable registries such as:

- `resource_managers`
- route template list
- relationship metadata collected from `Ref` annotations
- pending create actions
- pending update actions

Therefore:

- **Do** call `configure()`, `add_model()`, `add_route_template()`, `create_action()`,
  `update_action()` during application startup.
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
- register custom update action routes
- add ref-specific routes (referrers + relationships)
- add global backup/restore routes

## OpenAPI customization

`openapi()` mutates `app.openapi_schema` to inject:

- SpecStar-related schemas into `components.schemas`
- ref metadata extensions (`x-ref-*`, `x-ref-revision-*`) on schema properties
- top-level extension for custom create actions (`x-specstar-custom-create-actions`)
- top-level extension for custom update actions (`x-specstar-custom-update-actions`)

In most cases you don't need to call `openapi()` manually because it is used by `apply()` flows.

## Practical startup checklist

For a predictable setup, follow this order:

1. create or import the SpecStar instance
2. call `configure()` if you need custom defaults
3. register all models
4. add route templates or custom actions
5. call `apply()` once startup wiring is ready

Treat steps 2–4 as startup-time operations rather than request-time operations.

## Common failure patterns

If your app behaves unexpectedly, the most common causes are:

- calling `configure()` too late
- registering models after startup has already moved on
- mutating routes or templates after `apply()`
- confusing initialization issues with revision lifecycle issues
- mixing the global instance pattern with ad-hoc manual instances without realizing which one owns the routes

For symptom-to-fix guidance, see the [troubleshooting guide](/specstar/howto/troubleshooting).
