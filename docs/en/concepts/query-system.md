# Query System

SpecStar provides two ways to express search queries:

- the recommended **Query Builder** expression, passed through the `qb` query parameter or used directly in Python
- structured JSON query inputs such as `data_conditions`, `conditions`, and `sorts`

For most applications, **QB is the preferred interface** because it is more readable, supports nested logic, and is parsed safely with an AST-based parser instead of `eval`.

If you want the full list of supported helpers, operators, and metadata accessors, use the [Query Builder reference](/specstar/reference/query-builder) alongside this overview.

---

# Query Builder (`QB`)

`QB` provides Python-like syntax for building search filters.

HTTP examples:

```text
qb=QB["age"] > 18
qb=(QB["age"] > 18) & (QB["status"] == "active")
qb=QB["age"].gt(18).sort("-created_time").page(2, 20)
```

Python example:

```python
from specstar.query import QB

query = (
    (QB["age"] > 18)
    & QB["status"].eq("active")
).sort("-created_time").page(1, 20)

results = manager.search_resources(query)
```

---

# Data field queries

Data fields use bracket notation:

```python
QB["field_name"]
```

Examples:

```python
QB["name"] == "Alice"
QB["age"] > 18
QB["price"] >= 100
QB["user.email"] == "alice@example.com"
```

Field paths may include dots or special characters because the field name is always passed as a string:

```python
QB["class"]
QB["field-name"]
QB["some.field.with.dots"]
```

---

# Resource metadata fields

`QB` also exposes helper accessors for resource metadata stored on `ResourceMeta`.

| Field | Meaning |
|------|---------|
| `QB.resource_id()` | Resource identifier |
| `QB.current_revision_id()` | The current revision ID |
| `QB.created_time()` | Resource creation time |
| `QB.updated_time()` | Resource last update time |
| `QB.created_by()` | Creator |
| `QB.updated_by()` | Last updater |
| `QB.is_deleted()` | Soft-delete flag |
| `QB.schema_version()` | Current schema version |
| `QB.total_revision_count()` | Total number of revisions |
| `QB.rev_status()` | Status of the current revision (`draft` / `stable`) |
| `QB.rev_created_by()` | User who created the current revision |
| `QB.rev_updated_by()` | User who last updated the current revision |
| `QB.rev_created_time()` | When the current revision was created |
| `QB.rev_updated_time()` | When the current revision was last updated |

Examples:

```python
QB.resource_id().starts_with("user-")
QB.created_time() >= datetime.datetime(2024, 1, 1)
QB.updated_by().ne("guest")
QB.is_deleted().is_false()
QB.rev_status().eq("draft")
QB.rev_created_by().one_of(["alice", "bob"])
QB.rev_created_time().last_n_days(7)
```

> Filtering and built-in metadata sorting both work for all of the accessors above. The `rev_*` accessors target the **current revision** only; they are denormalized mirror fields kept in sync by SpecStar, so no extra revision reads are needed.

---

# Logical operators

QB supports nested boolean logic.

## AND (`&`)

```python
(QB["age"] > 18) & (QB["status"] == "active")
```

Equivalent to:

```python
QB.all(QB["age"] > 18, QB["status"] == "active")
```

## OR (`|`)

```python
(QB["status"] == "draft") | (QB["status"] == "review")
```

Equivalent to:

```python
QB.any(
    QB["status"] == "draft",
    QB["status"] == "review",
)
```

## NOT (`~`)

```python
~QB["archived"].eq(True)
```

---

# `QB.all()` and `QB.any()`

Use these helpers when you want to build grouped conditions more explicitly.

### AND group

```python
QB.all(
    QB["age"] > 18,
    QB["status"] == "active",
    QB["score"] >= 80,
)
```

`QB.all()` with no arguments matches all resources.

### OR group

```python
QB.any(
    QB["status"] == "draft",
    QB["status"] == "pending",
    QB["status"] == "review",
)
```

`QB.any()` requires at least one condition.

---

# Common helper methods

QB includes more than basic comparison operators. Common helpers include:

- comparison: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `between`, `in_range`
- strings: `contains`, `starts_with`, `ends_with`, `icontains`, `regex`, `match`, `like`
- collections: `in_`, `not_in`, `one_of`
- null and value checks: `is_null`, `is_not_null`, `has_value`, `is_empty`, `is_blank`
- boolean helpers: `is_true`, `is_false`, `is_truthy`, `is_falsy`
- grouping helpers: `filter`, `exclude`, `all`, `any`
- sorting and pagination: `sort`, `order_by`, `limit`, `offset`, `page`, `first`
- date helpers: `today`, `yesterday`, `this_week`, `this_month`, `this_year`, `last_n_days`
- transforms: `length()` for string or collection length checks

---

# HTTP usage

For HTTP APIs, pass the expression as the `qb` query parameter.

```text
GET /user?qb=QB["age"].gt(18)
GET /user?qb=(QB["age"] > 18) & QB["status"].eq("active")
GET /user?qb=QB.created_by().eq("admin")
```

In real clients, the query string should be URL-encoded automatically.

## Conflict rules

When `qb` is present, do not also send:

- `data_conditions`
- `conditions`
- `sorts`
- time-range or user filter parameters: `created_time_start`, `created_time_end`, `updated_time_start`, `updated_time_end`, `created_bys`, `updated_bys`
- revision filter parameters: `rev_statuses`, `rev_created_bys`, `rev_updated_bys`, `rev_created_time_start`, `rev_created_time_end`, `rev_updated_time_start`, `rev_updated_time_end`

That combination is rejected by the API. Instead, include those conditions directly in the QB expression — for example `QB.rev_status().eq("draft")` or `QB.rev_created_time().last_n_days(7)`.

## Pagination behavior

You can still pass `limit` and `offset` in the URL:

```text
GET /users?qb=QB["age"].gt(18)&limit=20&offset=40
```

List-style endpoints are paginated by default. The startup default comes from the SPECSTAR_DEFAULT_QUERY_LIMIT environment variable, and you can still override it per request with an explicit limit.

If both are present, the URL values override any `.limit()`, `.offset()`, or `.page()` settings defined inside the QB expression.

When `qb` mode is used, treat the QB expression as the main filter definition. In practice, if you need delete-status filtering, express it inside QB itself, for example with `QB.is_deleted().is_false()`.

## Error behavior

- an invalid QB expression returns a client error
- combining `qb` with the conflicting JSON query parameters returns a validation error

---

# QB vs JSON conditions

SpecStar still supports the lower-level JSON query parameters for clients that prefer explicit structured payloads.

Use QB when you want:

- more readable expressions
- nested boolean logic
- less manual JSON encoding
- one query string that maps closely to Python usage

Use the JSON parameters when you are generating requests mechanically from another tool.

---

# Examples

### Basic filter

```text
GET /users?qb=QB["age"] > 18
```

### Multiple conditions

```text
GET /users?qb=(QB["age"] > 18) & (QB["status"] == "active")
```

### Metadata query

```text
GET /users?qb=QB.created_by().eq("admin")
```

### Date filter

```text
GET /orders?qb=QB.created_time() >= datetime.datetime(2024, 1, 1)
```

### Complex query

```text
GET /users?qb=QB.all(
    QB["age"] > 18,
    QB.any(
        QB["status"] == "active",
        QB["status"] == "trial",
    ),
)
```

---

# Summary

Key points:

- `QB` is the recommended query interface
- data fields use `QB["field"]`
- metadata fields use helpers such as `QB.resource_id()` and `QB.created_time()`
- conditions can be combined with `&`, `|`, `~`, `QB.all()`, and `QB.any()`
- the HTTP API accepts the expression through the `qb` query parameter

---

## Read next

- [Query Builder reference](/specstar/reference/query-builder)
- [Search indexing](/specstar/concepts/search-indexing)
- [Query Builder](/specstar/howto/query-builder)
- [Routes generation](/specstar/howto/routes)
- [Troubleshooting](/specstar/howto/troubleshooting)