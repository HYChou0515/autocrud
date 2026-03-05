# Errors & troubleshooting

This page summarizes the most common AutoCRUD exceptions and what to do when you see them.

## Quick map

### Permission / access
- `PermissionDeniedError`

### Not found
- `ResourceNotFoundError`
- `ResourceIDNotFoundError`
- `RevisionNotFoundError`
- `RevisionIDNotFoundError`
- `ResourceIsDeletedError`

### Conflicts / write failures
- `ResourceConflictError`
- `CannotModifyResourceError`
- `SchemaConflictError`
- `UniqueConstraintError`
- `DuplicateResourceError`

### Validation
- `ValidationError` (domain / business validation)
- `msgspec.ValidationError` (type-level validation; from msgspec)

---

## Permission

### PermissionDeniedError
**Meaning**: the current request/user is not allowed to perform the operation.

**What to check**
- whether your `permission_checker` is configured as expected (AllowAll vs RBAC/custom)
- whether the endpoint is protected by dependencies/guards in route templates

---

## Not found family

### ResourceIDNotFoundError
**Message**: `Resource '{resource_id}' not found.`

**Meaning**: no resource with that `resource_id` exists.

**Typical causes**
- client uses a wrong/old ID
- resource was never created
- resource was permanently deleted (if supported)

### ResourceIsDeletedError
**Message**: `Resource '{resource_id}' is deleted.`

**Meaning**: the resource exists but is **soft-deleted**.

**What to do**
- call the restore endpoint (if enabled) or use a restore method if using the manager API
- or explicitly query/include deleted resources if your API supports it

### RevisionIDNotFoundError
**Message**: `Revision '{revision_id}' of Resource '{resource_id}' not found.`

**Meaning**: the resource exists, but that specific revision does not.

**Typical causes**
- client uses a stale revision ID
- revision history was pruned (if you implement pruning)
- wrong resource_id + revision_id pairing

---

## Conflict family

### ResourceConflictError (base)
Base class for “write cannot proceed due to conflict” errors.

### CannotModifyResourceError
**Message**: `Resource '{resource_id}' cannot be modified.`

**Meaning**: the resource is in a state that disallows modification
(e.g. immutable status / locked / policy-based restriction — depends on your system).

**What to do**
- check revision status / permissions / any domain rules that gate modifications

### UniqueConstraintError
**Message**: `Unique constraint violated: field '{field}' value ... already exists on resource '{conflicting_resource_id}'.`

**Meaning**: a field annotated with `Unique()` is being set to a value already used by another
**non-deleted** resource.

**Important semantics**
- soft-deleted resources are ignored for uniqueness
- `None` values are ignored (`None` can repeat)

**How to fix**
- pick a different value, or
- delete/rename the conflicting resource, or
- restore/undelete logic if you expected it to be deleted, or
- remove `Unique()` if this field should not be globally unique

**Debug checklist**
- confirm the conflicting resource is not deleted
- confirm you are not accidentally writing the same value across two resources
- confirm indexes/search are working for your storage backend

### DuplicateResourceError (load only)
**Meaning**: during `load(...)`, a resource ID already existed and `on_duplicate=raise_error`
was chosen.

**How to fix**
- use `on_duplicate=overwrite` to replace existing resources, or
- use `on_duplicate=skip` to keep existing resources, or
- ensure your dump/import set does not contain duplicates

---

## Validation

### ValidationError (AutoCRUD domain validation)
`ValidationError` is raised when your custom validator fails.

Typical sources:
- `Schema(..., validator=...)`
- `add_model(..., validator=...)`
- `IValidator.validate(...)`

**How to debug**
- inspect the error message from your validator
- reproduce by running the same validator against the payload locally

### msgspec.ValidationError (type validation)
This indicates the payload does not match the declared schema type
(e.g. wrong type, missing required field).

**How to debug**
- check request body structure matches your msgspec Struct fields
- check optional fields and default values
- check union variants (if using union types)