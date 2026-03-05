# HTTP error mapping (route templates)

This page documents how AutoCRUD route templates map internal exceptions to HTTP responses.

> Important: Write routes intentionally normalize many internal exceptions into
> `400 Bad Request`. This behavior simplifies API usage but may change in
> future versions to expose more specific HTTP status codes.

---

# Error matrix (quick overview)

| Route | 400 | 404 | 409 | 422 |
|------|-----|-----|-----|-----|
| GET | generic read failure | resource / revision missing | — | — |
| POST | generic create error | — | unique constraint | validation |
| PUT | generic update error | — | unique constraint | validation |
| PATCH | generic patch failure (includes unique) | — | — | validation |

---

# Read routes (`get.py`) — current mapping

## Canonical GET resource

`GET /{model}/{resource_id}`  
(and deprecated aliases like `/data`, `/meta`, `/full`, `/revision-info`)

### Common errors

**404 Not Found**

Most internal exceptions are caught and returned as:

```python
HTTPException(404, detail=str(e))
```

This includes (but is not limited to):

* `ResourceIDNotFoundError`
* `ResourceIsDeletedError` (unless `include_deleted=true`)
* `RevisionIDNotFoundError`
* `RevisionNotFoundError`

### Notes

Read routes intentionally **do not distinguish** between:

* permission errors
* not-found errors
* conflict errors

All of these are normalized to `404`.

---

## Revision list

`GET /{model}/{resource_id}/revision-list`

### 400 Bad Request

* invalid `sort` value (must be `created_time` or `-created_time`)
* invalid `limit` (< 1)
* invalid `offset` (< 0)

### 404 Not Found

* `from_revision_id` does not exist
* any other internal exception during revision retrieval

---

## Blob content

`GET /{model}/{resource_id}/blobs/{file_id}`

This route performs a permission gate using:

```
resource_manager.get(resource_id)
```

### 403 Forbidden

Returned when permission check fails.

Currently this collapses:

* permission denied
* resource not found

into the same response.

### 404 Not Found

* blob does not exist (`FileNotFoundError`)

### 400 Bad Request

* blob store not configured (`NotImplementedError`)

### 500 Internal Server Error

* blob record exists but blob data is missing

```
detail: "Blob data missing"
```

---

# Create routes (`create.py`) — current mapping

## Create resource

`POST /{model}`

### 422 Unprocessable Entity

Validation errors during decoding or domain validation:

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

### 400 Bad Request

Any other exception during resource creation is normalized to:

```
HTTPException(400, detail=str(e))
```

Examples include:

* permission failures
* storage errors
* unexpected runtime exceptions

---

# Update routes (`update.py`) — current mapping

## Full replacement update

`PUT /{model}/{resource_id}`

### 400 Bad Request

* invalid argument combination
  (`change_status` is only allowed when `mode="modify"`)

* any other exception during update

Note that **resource not found is also normalized to 400**.

### 422 Unprocessable Entity

Validation failures:

* `msgspec.ValidationError`
* `autocrud.types.ValidationError`

### 409 Conflict

Unique constraint violation:

* `UniqueConstraintError`

Response body format is identical to the Create route.

### Notes

The update route currently **does not return 404**.

All not-found conditions are normalized to `400`.

---

# Patch routes (`patch.py`) — current mapping

## JSON Patch

`PATCH /{model}/{resource_id}`

Supports RFC6902 patch operations:

* `add`
* `remove`
* `replace`
* `move`
* `copy`
* `test`

### 400 Bad Request

Most runtime errors are normalized to `400`, including:

* resource not found
* revision not found
* permission failures
* JSON Patch failures
* invalid patch paths
* failed `test` operations
* unique constraint violations
* any other runtime exceptions

### 422 Unprocessable Entity

Validation errors:

* `msgspec.ValidationError`
* `autocrud.types.ValidationError`

### Notes

This route currently **does not return 404 or 409**.

All runtime errors except validation are normalized to `400`.

Additionally:

```
change_status can only be used with mode="modify"
```

Violating this rule also returns `400`.

---

# Implications for API clients

### Read operations

Clients should treat `404` as a generic **read failure**, which may represent:

* resource does not exist
* revision does not exist
* permission denied
* internal retrieval failure

### Write operations

Write routes intentionally normalize most failures to:

```
400 Bad Request
```

except for:

* `409` → unique constraint violation
* `422` → validation error

Clients should rely primarily on:

* `409` for uniqueness conflicts
* `422` for schema validation errors

---

# Recommended improvements (optional)

If a more REST-accurate API surface is desired in the future, the following changes may be considered:

* map `PermissionDeniedError` → `403`
* map `ResourceNotFoundError` → `404`
* map all `ResourceConflictError` subclasses → `409`
* avoid broad `except Exception` handlers that collapse errors into `400` or `404`
