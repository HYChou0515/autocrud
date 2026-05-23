# Counter-intuitive behaviors & gotchas

Quick reference for things that **look like a bug but aren't**. Each entry
explains the "intuitive guess" first, then what SpecStar actually does, and
links to the relevant guide.

If a behavior here genuinely bites you, please open an issue — most of
these are 0.x trade-offs that may sharpen up before 1.0.

---

## Reads / response shape

### `GET /{model}/{id}` returns an envelope, not the bare resource

| Intuitive guess | Actual behavior |
|-----------------|-----------------|
| `GET /user/123` → `{name: "...", email: "..."}` | `GET /user/123` → `{"data": {...}, "revision_info": {...}, "meta": {...}}` |

The envelope is intentional: the same endpoint can return data, revision
info, and metadata together. To get the bare data only:

* `GET /user/123/data` — single-section read, or
* `GET /user/123?returns=data` — same effect via `returns` selector.

See [API conventions](./api-conventions.md#canonical-read-api-get-modelresource_id).

### `?partial=true` on a list returns `data: {}` for every row

`partial` is a **field selector** (slash-prefixed paths), not a boolean.
`?partial=true` is normalised to the path `/true` which matches no field in
your struct, so the projector strips data down to an empty object. Use
slash-prefixed field names instead:

```
GET /user?partial=/name&partial=/email
```

See [API conventions § `partial`](./api-conventions.md#field-projection-partial-partial).

### Three id fields in every response

| Field | Where | Use for |
|-------|-------|---------|
| `resource_id` | `meta.resource_id` | URL paths, stable across revisions |
| `revision_id` | `revision_info.revision_id` | `switch`, revision-targeted reads |
| `uid` | `meta.uid` | **Internal — do not put in URLs** (differs per revision) |

---

## Lists & filters

### Bare `?field=value` query params are silently ignored

| Intuitive guess | Actual behavior |
|-----------------|-----------------|
| `GET /task?name=Alice` returns Alice's tasks | Returns *all* tasks; `name` is silently dropped |

Filtering goes through the structured `qb` DSL or `data_conditions` /
`conditions`. See [Query Builder](./query-builder.md).

### Default page size is effectively unlimited until you set it

`SPECSTAR_DEFAULT_QUERY_LIMIT` defaults to `2**32 - 1`. Set a sane limit
(e.g. `1000`) for production. Per-request `?limit=` overrides it.

### `limit=0` returns zero rows, not "all rows"

`limit` is the literal page size. `0` means "give me nothing." For all
rows, omit `limit` (or set it to a large finite number).

---

## Writes

### Unknown fields are silently dropped (until you opt in)

By default, `POST` / `PUT` with extra keys returns `200` and the extras
are gone. A typo'd field = lost data. Opt into strict mode:

```python
SpecStar(forbid_unknown_fields=True)
# or
spec.configure(forbid_unknown_fields=True)
```

With it on, unknown fields return `422`. See [API
conventions § Strictness](./api-conventions.md#strictness-unknown-fields-on-write).

### `resource_id` cannot be set through the request body

```
POST /note  {"title": "a", "resource_id": "my-id"}   # 422
PUT /note/<id>  {"title": "a", "resource_id": "x"}   # 422
PATCH /note/<id>  [{"op":"replace","path":"/resource_id","value":"x"}]  # 422
```

`resource_id` is server-generated at creation and immutable afterwards, so
it never belongs in `POST` / `PUT` / `PATCH` bodies. SpecStar rejects it with
`422` rather than silently dropping it (the previous behavior — see
[CHANGELOG](https://github.com/HYChou0515/specstar/blob/master/CHANGELOG.md)).
To customise how ids are generated, pass `id_generator=` to
`spec.add_model(...)`.

The one exception: if your Struct *legitimately* declares a field named
`resource_id`, the guard steps aside and treats it as ordinary data.

### `PUT` is full-replace, not upsert

| Intuitive guess | Actual behavior |
|-----------------|-----------------|
| `PUT /user/unknown-id` creates the user | Returns `404` — `PUT` requires the resource to exist. Use `POST /user` to create. |

### `PATCH` accepts two flavors — pick by shape (array = ops, object = merge)

`PATCH` understands **both** REST patch standards on the same endpoint:

```
PATCH /user/123  [{"op":"replace","path":"/name","value":"new"}]   # RFC 6902 JSON Patch (array)
PATCH /user/123  {"name": "new"}                                   # RFC 7386 Merge Patch (object)
```

A JSON **array** is treated as RFC 6902 operations; a JSON **object** is a
RFC 7386 merge patch (partial update; `null` deletes a field). Set
`Content-Type: application/json-patch+json` or `application/merge-patch+json`
to be explicit. See [API conventions § PATCH](./api-conventions.md#patch-two-flavors).

### Same-content writes are de-duplicated

A `PUT` that produces byte-identical content as the current revision
returns `200` but **does not create a new revision**. Compare the
returned `revision_id` to the prior one to detect a dedup. See [API
conventions § Revisions and mutability](./api-conventions.md#revisions-and-mutability).

### `DELETE` returns `200 + meta body`, not `204 No Content`

Useful when callers want the post-delete metadata (e.g. to confirm soft
delete, capture timestamps). If you only care about success, just check
`status_code < 300`.

### Soft-deleted resources return `410 Gone`, not `404`

Distinct from "never existed" `404`. Pass `?include_deleted=true` to
read them through the same endpoints.

---

## Versioning / migration

### Resources registered with bare `add_model(Model)` store `schema_version=None`

Later upgrading to `Schema(Model, "v2").step("v1", ...)` then fails with
"No migration path from version None to 'v2'". Two recoveries:

1. **Recommended from day one:** always use `Schema(Model, "v1")` even
   before you have migrations.
2. **Already have unversioned data:** register a `step(None, ...)`
   migration. See [Migrations howto](./migrations.md#migrating-from-unversioned-schema_versionnone-data).

### `switch` needs the full `revision_id` *or* a bare revision number

Both forms work; anything else returns `400` with a hint:

```
POST /user/{rid}/switch/3                  # OK — normalised to {rid}:3
POST /user/{rid}/switch/{rid}:3            # OK — explicit
POST /user/{rid}/switch/whatever           # 400 — invalid format
```

### `switch` to an older revision may raise `RevisionNotMigratedError`

After `migrate(resource_id)` bumps `meta.schema_version` to the new
target, older revisions still sit at their original `schema_version`.
`switch` to one of those raises `RevisionNotMigratedError` (400). Fix
by migrating that specific revision first:

```python
rm.migrate(resource_id, revision_id=old_revision_id)
rm.switch(resource_id, old_revision_id)
```

---

## Configuration

### `configure(admin=...)` sets the RBAC root **user name**, not a URL path

```python
spec.configure(admin="alice")   # username "alice" gets full access
spec.configure(admin="/admin")  # username "/admin" — almost certainly NOT what you wanted
```

The web admin UI is the separate TypeScript app under `wizard/`.

### Programmatic `mgr.create/update/migrate/switch` need an operation context

Without one, they raise `MissingOperationContextError` (which surfaces as
a bare `LookupError` for the underlying `ContextVar`). Either:

```python
spec.configure(default_user="me", default_now=datetime.utcnow)
# or, per-call
with mgr.using(user="me", now=datetime.utcnow()):
    mgr.create(...)
```

### `MigrateRouteTemplate` is opt-in

`/{model}/migrate/...` endpoints are **not** registered by default.
Add them explicitly before `add_model()`:

```python
from specstar.crud.route_templates.migrate import MigrateRouteTemplate
spec.add_route_template(MigrateRouteTemplate())
```

The mounted paths follow `model_naming` and are singular —
`/issue/migrate/execute`, not `/issues/migrate/execute`.

---

## Backup / restore

### `/import` accepts `multipart/form-data` even though `/export` returns raw bytes

`GET /{model}/export` streams `application/octet-stream`, but
`POST /{model}/import` expects `multipart/form-data` with a `file`
field. Sending the export body raw → `422`. See [Backup &
Restore](./backup-restore.md#per-model-import) for a `curl` recipe.

---

## GraphQL is opt-in

The README lists GraphQL as a feature; that means *supported*, not
*on by default*. To use it:

```bash
pip install specstar[graphql]
```

```python
from specstar.crud.route_templates.graphql import GraphQLRouteTemplate
spec.add_route_template(GraphQLRouteTemplate())
```

---

## Naming / paths

### Multi-word class names are kebab-cased, not snake-cased

`BlogPost → /blog-post`, `XMLNode → /x-m-l-node`. The default
`model_naming="kebab"` is lowercase with hyphens; see [Routes howto §
`model_naming` reference](./routes.md#model_naming-reference) for a full
matrix and an example of supplying a callable (e.g. to pluralise).

### Path params are always `resource_id`, not `id`

`GET /user/{resource_id}` — there is no `/user/{id}`. Same for every
generated route.
