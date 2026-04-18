# Troubleshooting

This page helps you diagnose the most common AutoCRUD issues in real projects.

Use it when something is failing and you need a practical path from symptom to likely fix.

---

## 1. The app starts, but behavior seems inconsistent

### Symptoms

- routes are missing
- model changes do not appear as expected
- the app behaves differently after dynamic reconfiguration

### What to check

- call `configure()` during startup, not after the app is already serving requests
- register all models before `apply()`
- avoid mutating route templates and model registration after startup

See also:

- [Behavior reference](/autocrud/reference/behavior)

---

## 2. A write fails with a conflict

### Common causes

- a `Unique()` field already exists on another active resource
- you are trying to modify a resource in a disallowed state
- the target revision schema does not match the current schema version

### What to check

- whether the conflicting value is already in use
- whether the resource is soft-deleted rather than missing
- whether a migration is required before switching or reusing an older revision

See also:

- [Errors](/autocrud/howto/errors)
- [Constraints](/autocrud/howto/constraints)
- [Validation](/autocrud/concepts/validation)
- [Schema migration](/autocrud/quickstart/schema-migration)

---

## 3. Permission denied errors

### Symptoms

- requests return access-denied behavior even though the route exists
- a user can read but not update
- ACL or RBAC rules seem to be ignored

### What to check

- which permission checker is configured
- whether your current user matches the intended subject or role
- whether the action being blocked is `read`, `update`, `delete`, or a grouped action
- whether a strict default-deny policy is active with no matching allow rule

See also:

- [Permissions](/autocrud/howto/permissions)

---

## 4. Search returns nothing

### Common causes

- the field you are searching is not indexed
- the query operator is wrong for the field type
- the resource is soft-deleted and the current query excludes deleted data

### What to check

- confirm the target field is indexed
- confirm the operator matches the expected value type
- test with a simpler query first, then add more conditions gradually
- if results look truncated rather than missing, pass an explicit `limit` or set `AUTOCRUD_DEFAULT_QUERY_LIMIT` at startup
- use the `/count` endpoint when you need the exact total number of matches

See also:

- [Query builder](/autocrud/howto/query-builder)
- [Query system](/autocrud/concepts/query-system)
- [Search indexing](/autocrud/concepts/search-indexing)
- [Routes generation](/autocrud/howto/routes)

---

## 5. Blob or file upload problems

### Symptoms

- uploads fail partway through
- the file metadata exists but the content is not accessible
- large uploads stall or do not finalize

### What to check

- whether the blob route template is enabled
- whether the selected blob backend is configured correctly
- whether the upload session was finalized successfully
- whether the backend expects proxy upload or direct upload via `single_put`

See also:

- [Binary data](/autocrud/howto/binary-data)
- [API conventions](/autocrud/howto/api-conventions)

---

## 6. Backup and restore issues

### Symptoms

- imported data does not appear
- duplicate IDs cause load failures
- only part of the dataset is restored

### What to check

- which `on_duplicate` strategy was used
- whether you exported the correct model or the whole environment
- whether the target storage backend was initialized correctly before import

See also:

- [Backup and restore](/autocrud/howto/backup-restore)
- [From demo to production](/autocrud/guides/from-demo-to-production)

---

## 7. Pydantic model surprises

### Symptoms

- dict input works differently than expected
- validators reject payloads that look valid at first glance
- output shapes differ from your Pydantic model objects

### What to check

- whether the resource was registered as a Pydantic model
- whether the validation error comes from Pydantic or from an AutoCRUD domain rule
- whether you are assuming the stored output remains a Pydantic instance internally

See also:

- [Pydantic integration](/autocrud/howto/pydantic-integration)
- [Validation](/autocrud/concepts/validation)

---

## 8. Queue or job issues

### Symptoms

- jobs remain pending
- a worker never picks up the task
- retries happen unexpectedly or not at all

### What to check

- whether the message queue backend is actually running
- whether the consumer has started
- whether the handler raised an exception and moved the job into failure state

See also:

- [Job queue quickstart](/autocrud/quickstart/job-queue)

---

## General debugging advice

When diagnosing AutoCRUD issues, start by narrowing the problem to one layer:

1. model and validation
2. resource lifecycle
3. permissions and events
4. storage or blob backend
5. queue or integration layer

That usually makes the real cause much easier to find.
