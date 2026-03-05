# API conventions

This document describes AutoCRUD’s **HTTP API conventions** — especially the parts that are *not* obvious from plain REST CRUD:
- `returns=` (select response sections)
- `partial=` (field-level projection across `data` / `meta` / `revision_info`)
- `include_deleted=` (soft-delete visibility)
- revisions & versioning semantics
- blob (`Binary`) handling
- query / search conventions (`qb` recommended)

> This document reflects the current implementation in route templates.

---

## Canonical read API: `GET /{model}/{resource_id}`

### Response shape (section-based)
AutoCRUD returns a unified response envelope:

```json
{
  "data": "...",
  "revision_info": "...",
  "meta": "..."
}
```

Each section can be **included or omitted** via `returns`.

### `returns` query parameter

`returns` is a comma-separated list of sections to include.

* Allowed values:

  * `data`
  * `revision_info`
  * `meta`

* Default:

  * `returns=data,revision_info,meta`

Examples:

* Full response (default)

  `GET /users/123`

* Data only

  `GET /users/123?returns=data`

* Meta only

  `GET /users/123?returns=meta`

* Data + meta (no revision info)

  `GET /users/123?returns=data,meta`

> Note: Any section not listed in `returns` will be returned as `UNSET` (omitted in the serialized output, depending on encoder behavior).

---

## Field projection: `partial` / `partial[]`

AutoCRUD supports field-level projection through `partial` (or `partial[]` for axios / repeated-query compatibility).

### The `partial` path format

* Paths are **slash-prefixed**:

  * `/field`
  * `/nested/field`
* If the user passes `field` (no leading slash), AutoCRUD normalizes it to `/field`.

> `partial` is treated as a structural selector (similar to JSON Pointer style paths), and is passed into `filter_struct_partial()` / `get_partial()`.

### Prefix routing: project across `data`, `meta`, `revision_info`

Each `partial` field can be routed to a specific section by using a prefix:

* `data/<path>` → applies to `data`
* `meta/<path>` → applies to `meta`
* `info/<path>` → applies to `revision_info` (**note the prefix is `info/`, section name is `revision_info`)

Examples:

* Only some fields of `data`

  `GET /users/123?returns=data&partial=/name&partial=/email`

* Only some fields of `meta`

  `GET /users/123?returns=meta&partial=meta/resource_id&partial=meta/updated_time`

* Only some fields of `revision_info`

  `GET /users/123?returns=revision_info&partial=info/revision_id&partial=info/status`

* Mixed projection across multiple sections

  `GET /users/123?returns=data,meta&partial=/name&partial=meta/updated_time`

### Default routing of unprefixed `partial`

Unprefixed `partial` paths are routed by the route’s `default_category`.

For canonical `GET /{model}/{resource_id}`:

* `default_category = "data"`
* Therefore:

  * `partial=/name` → applies to **data**
  * If you want meta/info, you must prefix with `meta/` or `info/`.

For legacy endpoints (deprecated aliases) the default category differs:

* `/meta` endpoints set `default_category="meta"`
* `/revision-info` endpoints set `default_category="info"`

---

## Soft deletion: `include_deleted`

Most read endpoints accept:

* `include_deleted=false` (default)
* `include_deleted=true`

### Behavior (read)

`include_deleted` controls whether metadata can be retrieved for soft-deleted resources.

At the `ResourceManager` layer:

* `get_meta(resource_id, include_deleted=False)`:

  * raises `ResourceIsDeletedError` if resource is deleted
* `get_meta(resource_id, include_deleted=True)`:

  * returns metadata even if deleted

Route templates typically call `get_meta(...)` first, so `include_deleted` is a **visibility switch** that gates follow-up reads (data, revision info, etc.).

> Note: Current read routes collapse most errors into HTTP 404 (see “HTTP error mapping”).

---

## Revisions and mutability

AutoCRUD has two update modes with different revision semantics:

### `update` (default): append a new revision (immutable history)

* Used by:

  * `PUT /{model}/{resource_id}` with `mode=update` (default)
  * `PATCH /{model}/{resource_id}` with `mode=update` (default)
* Semantics:

  * Creates a **new revision**
  * Sets `parent_revision_id` to the previous current revision
  * Revision history is append-only under this mode

### `modify` (draft update): overwrite the current revision (not immutable)

* Used by:

  * `PUT /{model}/{resource_id}?mode=modify`
  * `PATCH /{model}/{resource_id}?mode=modify`
* Semantics:

  * **Overwrites** the current revision instead of creating a new one
  * This means the revision history is **not immutable** under `modify`
  * `change_status` is only allowed under `mode=modify`

> Practical guidance:
>
> * Use `update` for normal production writes / audit history.
> * Use `modify` for draft workflows where “current revision is editable”.

---

## Blob conventions (`Binary`)

AutoCRUD supports a first-class blob type:

```python
class Binary(Struct):
    file_id: str | UNSET
    size: int | UNSET
    content_type: str | UNSET
    data: bytes | UNSET
```

### Storage behavior

When writing a resource that contains `Binary(data=...)`:

* AutoCRUD extracts the bytes
* Stores them into the configured `IBlobStore`
* Populates:

  * `file_id` (hash of content)
  * `size`
  * optionally `content_type`
* Clears `data` in the stored resource (so resource payload stays small)

### Read behavior

Blob bytes are retrieved via the dedicated endpoint:

`GET /{model}/{resource_id}/blobs/{file_id}`

* This endpoint performs a **permission gate** by calling `resource_manager.get(resource_id)` first.
* Then it calls `resource_manager.get_blob(file_id)` to fetch bytes.
* The response `Content-Type` uses:

  * `content_type` from `Binary` if available
  * otherwise `application/octet-stream`

---

## Query / search conventions (recommended: `qb`)

For list/search endpoints, AutoCRUD supports multiple query styles, but **recommends `qb`**.

### `qb` (recommended)

`qb` is a Query Builder expression parsed by a safe AST parser (not `eval`).

Example:

* `qb=QB["age"].gt(18) & QB["status"].eq("active")`

Rules:

* If `qb` is provided, it **must not** be combined with:

  * `data_conditions`
  * `conditions`
  * `sorts`
* `limit` / `offset` in URL can override defaults.

### Structured JSON conditions

If not using `qb`, you can pass JSON strings:

* `data_conditions`: filters over resource data fields
* `conditions`: general filters (meta or data depending on operator / field_path usage)
* `sorts`: mix of meta-sort and data-sort objects

These are parsed via `json.loads(...)` and converted into:

* `DataSearchCondition`
* `ResourceMetaSearchSort`
* `ResourceDataSearchSort`

---

## HTTP error mapping (route templates)

This section documents how current route templates map internal exceptions to HTTP responses.

> Some routes intentionally normalize multiple internal errors into the same HTTP code.

### Read routes (`get.py`)

#### Canonical GET resource

`GET /{model}/{resource_id}` (and deprecated aliases like `/data`, `/meta`, `/full`, `/revision-info`)

* **404 Not Found**

  * Most internal exceptions are caught and returned as:

    * `HTTPException(404, detail=str(e))`

This includes (but is not limited to):

* `ResourceIDNotFoundError`
* `ResourceIsDeletedError` (unless `include_deleted=true`)
* `RevisionIDNotFoundError`
* `RevisionNotFoundError`

**Note**

* Read routes currently do **not** consistently distinguish `404` vs `403` vs `409`.
  Many failures collapse into `404`.

#### Revision list

`GET /{model}/{resource_id}/revision-list`

* **400 Bad Request**

  * invalid `sort` (must be `created_time` or `-created_time`)
  * invalid `limit` (`< 1`)
  * invalid `offset` (`< 0`)

* **404 Not Found**

  * `from_revision_id` provided but not found (`detail="revision_id not found"`)
  * any other unhandled exception normalized to 404

#### Blob content

`GET /{model}/{resource_id}/blobs/{file_id}`

* **403 Forbidden**

  * permission gate fails (permission denied OR resource not found are currently collapsed)

* **404 Not Found**

  * `FileNotFoundError` (blob missing)

* **400 Bad Request**

  * `NotImplementedError` (blob store not configured)

* **500 Internal Server Error**

  * blob record exists but `data` is missing (`detail="Blob data missing"`)

### Create routes (`create.py`)

`POST /{model}`

* **422 Unprocessable Entity**

  * `msgspec.ValidationError` (type-level validation during decoding)
  * `autocrud.types.ValidationError` (domain/business validation)

* **409 Conflict**

  * `UniqueConstraintError` → mapped via helper (`raise_unique_conflict`)

* **400 Bad Request**

  * any other exception normalized to 400

### Update routes (`update.py`)

`PUT /{model}/{resource_id}`

* **400 Bad Request**

  * invalid argument combination: `change_status` only allowed with `mode=modify`
  * any other exception normalized to 400 (including “not found” today)

* **422 Unprocessable Entity**

  * `msgspec.ValidationError`
  * `autocrud.types.ValidationError`

* **409 Conflict**

  * `UniqueConstraintError` → mapped via helper (`raise_unique_conflict`)

**Note**

* Update route currently does **not** return 404; “resource not found” is folded into 400.

### Patch routes (`patch.py`)

`PATCH /{model}/{resource_id}`

* **400 Bad Request**

  * most runtime errors normalized to 400:

    * resource not found / revision not found
    * permission denied
    * jsonpatch apply failures (invalid path, test op failed, etc.)
    * other unhandled exceptions

* **422 Unprocessable Entity**

  * `msgspec.ValidationError`
  * `autocrud.types.ValidationError`

**Note**

* `change_status` is only valid with `mode=modify`; otherwise returns 400.

---

## Recommended client-side conventions

* Treat `404` on read endpoints as a generic “cannot fetch”.
  If you need to distinguish permission vs not-found, you must apply a stricter mapping
  (e.g. explicit exception handlers) or adjust templates.

* Prefer `qb` for search/list queries:

  * easier to version and safer than ad-hoc JSON conditions

* Use `update` mode for immutable audit history; use `modify` for draft workflows.

---

## Optional future improvements

If you want more REST-accurate mapping, consider:

* `PermissionDeniedError` → 403
* `ResourceNotFoundError` family → 404
* `ResourceConflictError` family (`UniqueConstraintError`, `DuplicateResourceError`, etc.) → 409
* avoid broad `except Exception` → 404/400 (it can hide real server bugs)
