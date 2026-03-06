# HTTP error mapping (route templates)

This page documents how AutoCRUD route templates map internal exceptions to HTTP responses.

All route templates use a **shared helper** (`to_http_exception`) that
provides consistent error mapping across every endpoint.

---

## Exception mapping table

| Exception                          | HTTP | Meaning              |
|------------------------------------|------|----------------------|
| `msgspec.ValidationError`          | 422  | Type-level validation |
| `autocrud.types.ValidationError`   | 422  | Custom validation     |
| `PermissionDeniedError`            | 403  | Access denied         |
| `ResourceNotFoundError` (family)   | 404  | Resource / revision missing |
| `UniqueConstraintError`            | 409  | Unique field conflict (structured detail) |
| `ResourceConflictError` (family)   | 409  | Conflict              |
| Any other `Exception`              | 400  | Bad request (fallback) |

The **ResourceNotFoundError** family includes:

* `ResourceIDNotFoundError`
* `ResourceIsDeletedError`
* `RevisionNotFoundError`
* `RevisionIDNotFoundError`

The **ResourceConflictError** family includes:

* `UniqueConstraintError` (structured JSON detail)
* `DuplicateResourceError`
* `SchemaConflictError`
* `CannotModifyResourceError`

---

## Error matrix (quick overview)

| Route   | 400          | 403         | 404             | 409              | 422        |
|---------|--------------|-------------|-----------------|------------------|------------|
| GET     | fallback     | permission  | not found       | conflict         | —          |
| POST    | fallback     | permission  | not found       | unique / conflict| validation |
| PUT     | fallback     | permission  | not found       | unique / conflict| validation |
| PATCH   | fallback     | permission  | not found       | unique / conflict| validation |
| DELETE  | fallback     | permission  | not found       | conflict         | —          |
| SWITCH  | fallback     | permission  | not found       | conflict         | —          |
| RESTORE | fallback     | permission  | not found       | conflict         | —          |

---

## Read routes (`get.py`)

### Canonical GET resource

`GET /{model}/{resource_id}`
(and deprecated aliases: `/data`, `/meta`, `/full`, `/revision-info`)

Errors pass through `to_http_exception`:

* **404** — `ResourceIDNotFoundError`, `ResourceIsDeletedError`, `RevisionIDNotFoundError`
* **403** — `PermissionDeniedError`
* **400** — any other internal exception

### Revision list

`GET /{model}/{resource_id}/revision-list`

Specific inline errors:

* **400** — invalid `sort`, `limit < 1`, `offset < 0`
* **404** — `from_revision_id` not found

All other exceptions go through `to_http_exception`.

### Blob content

`GET /{model}/{resource_id}/blobs/{file_id}`

The route performs a permission gate via `resource_manager.get(resource_id)`.
Errors from that call go through `to_http_exception`:

* **403** — `PermissionDeniedError`
* **404** — `ResourceIDNotFoundError`

Blob-specific errors:

* **404** — blob does not exist (`FileNotFoundError`)
* **400** — blob store not configured (`NotImplementedError`)
* **500** — blob data missing

---

## Create routes (`create.py`)

`POST /{model}`

### 422 Unprocessable Entity

Validation errors (caught explicitly before the fallback):

* `msgspec.ValidationError`
* `autocrud.types.ValidationError`

### 409 Conflict

Unique constraint violations:

* `UniqueConstraintError`

Response body (`detail`) format:

```json
{
  "message": "Unique constraint violated: field 'email' value 'foo@bar.com' already exists",
  "field": "email",
  "conflicting_resource_id": "user_123"
}
```

### Fallback

All other exceptions go through `to_http_exception` (403, 404, 409, or 400).

---

## Update routes (`update.py`)

`PUT /{model}/{resource_id}`

### 400 Bad Request (inline)

* `change_status` is only allowed when `mode="modify"`

### 422 Unprocessable Entity

Validation errors (caught explicitly):

* `msgspec.ValidationError`
* `autocrud.types.ValidationError`

### 409 Conflict

* `UniqueConstraintError` (structured detail, same as Create)
* `CannotModifyResourceError` (e.g. modifying a stable resource without `mode="modify"`)

### 404 Not Found

* `ResourceIDNotFoundError` — resource does not exist

### Fallback

All other exceptions go through `to_http_exception`.

---

## Patch routes (`patch.py`)

`PATCH /{model}/{resource_id}`

Supports RFC6902 patch operations: `add`, `remove`, `replace`, `move`, `copy`, `test`.

### 422 Unprocessable Entity

Validation errors (caught explicitly):

* `msgspec.ValidationError`
* `autocrud.types.ValidationError`

### 409 Conflict

* `UniqueConstraintError` (structured detail)

### 404 Not Found

* `ResourceIDNotFoundError`

### Fallback

All other exceptions go through `to_http_exception`.

---

## Delete routes (`delete.py`)

`DELETE /{model}/{resource_id}`

All exceptions go through `to_http_exception`:

* **404** — resource not found
* **403** — permission denied
* **409** — conflict
* **400** — fallback

The same mapping applies to:

* `DELETE /{model}/{resource_id}/permanently`
* `DELETE /{model}` (batch delete)
* `POST /{model}/{resource_id}/restore`
* `POST /{model}/restore` (batch restore)

---

## Switch routes (`switch.py`)

`POST /{model}/{resource_id}/switch/{revision_id}`

All exceptions go through `to_http_exception`:

* **404** — resource or revision not found
* **403** — permission denied
* **400** — fallback

---

## Implications for API clients

### Consistent behavior across all routes

All routes now use the same error mapping:

* **403** → access denied
* **404** → resource or revision does not exist
* **409** → conflict (unique constraint, cannot modify, duplicate, schema conflict)
* **422** → data validation failure
* **400** → generic / unexpected error

### UniqueConstraintError detail

`409` responses from `UniqueConstraintError` include structured JSON:

```json
{
  "message": "Unique constraint violated: ...",
  "field": "email",
  "conflicting_resource_id": "user_123"
}
```

Other `409` responses have a plain string `detail`.

---

## Implementation

The shared helper lives in `autocrud/crud/route_templates/exception_handlers.py`:

```python
from autocrud.crud.route_templates.exception_handlers import to_http_exception
```

Route templates use it as:

```python
except (msgspec.ValidationError, ValidationError) as e:
    raise HTTPException(status_code=422, detail=str(e))
except UniqueConstraintError as e:
    raise_unique_conflict(e)
except Exception as e:
    raise to_http_exception(e)
```
