# Query System

AutoCRUD provides a flexible query system for searching resources.

The recommended method is the **Query Builder (QB)** syntax, which allows
expressive queries using a safe AST-based parser.

This page describes:

- the Query Builder (`QB`)
- how to query resource metadata and data fields
- logical operators
- how queries are passed through HTTP APIs

---

# Query Builder (`QB`)

The `QB` class provides a Python-style syntax for building queries.

Example:

```

qb=QB["age"] > 18

```

Example with multiple conditions:

```

qb=(QB["age"] > 18) & (QB["status"] == "active")

```

This syntax is parsed safely using an AST parser rather than `eval`.

---

# Data field queries

Data fields are accessed using bracket notation.

```

QB["field_name"]

```

Examples:

```

QB["name"] == "Alice"
QB["age"] > 18
QB["price"] >= 100

```

Nested fields are supported:

```

QB["user.email"] == "[alice@example.com](mailto:alice@example.com)"

```

Field names with special characters are supported:

```

QB["class"]
QB["field-name"]
QB["some.field.with.dots"]

```

---

# Resource metadata fields

`QB` also provides built-in accessors for resource metadata.

These correspond to fields stored in **ResourceMeta**.

| Field | Description |
|------|-------------|
| `QB.resource_id()` | Resource identifier |
| `QB.revision_id()` | Current revision ID |
| `QB.created_time()` | Resource creation timestamp |
| `QB.updated_time()` | Resource last update timestamp |
| `QB.created_by()` | Creator |
| `QB.updated_by()` | Last updater |
| `QB.is_deleted()` | Soft delete status |
| `QB.schema_version()` | Resource schema version |
| `QB.total_revision_count()` | Number of revisions |

Examples:

```

QB.resource_id().eq("abc-123")

QB.created_time() >= datetime(2024, 1, 1)

QB.updated_by().ne("guest")

QB.is_deleted() == False

```

---

# Logical operators

QB supports logical combinations.

## AND (`&`)

```

(QB["age"] > 18) & (QB["status"] == "active")

```

Equivalent to:

```

QB.all(QB["age"] > 18, QB["status"] == "active")

```

---

## OR (`|`)

```

(QB["status"] == "draft") | (QB["status"] == "review")

```

Equivalent to:

```

QB.any(
QB["status"] == "draft",
QB["status"] == "review"
)

```

---

# `QB.all()` and `QB.any()`

These helper functions combine multiple conditions.

### AND group

```

QB.all(
QB["age"] > 18,
QB["status"] == "active",
QB["score"] >= 80
)

```

Equivalent to:

```

(QB["age"] > 18) &
(QB["status"] == "active") &
(QB["score"] >= 80)

```

If no conditions are provided:

```

QB.all()

```

This matches **all resources**.

---

### OR group

```

QB.any(
QB["status"] == "draft",
QB["status"] == "pending",
QB["status"] == "review"
)

```

Equivalent to:

```

(QB["status"] == "draft") |
(QB["status"] == "pending") |
(QB["status"] == "review")

```

`QB.any()` requires at least one condition.

---

# HTTP usage

Queries are passed via the `qb` query parameter.

Example:

```

GET /users?qb=QB["age"] > 18

```

Example with multiple conditions:

```

GET /users?qb=(QB["age"] > 18) & (QB["status"] == "active")

```

Example using metadata fields:

```

GET /users?qb=QB.created_by().eq("admin")

```

---

# Limit and offset

Pagination is controlled separately:

```

GET /users?qb=QB["age"] > 18&limit=20&offset=40

```

These parameters override defaults defined in the query builder.

---

# QB vs JSON conditions

AutoCRUD also supports structured JSON query parameters:

- `data_conditions`
- `conditions`
- `sorts`

However **QB is recommended** because:

- it is easier to read
- it supports nested logic
- it avoids complex JSON encoding
- it is parsed safely using AST

If `qb` is provided, it **cannot be combined** with:

```

data_conditions
conditions
sorts

```

---

# Examples

### Basic filter

```

GET /users?qb=QB["age"] > 18

```

---

### Multiple conditions

```

GET /users?qb=(QB["age"] > 18) & (QB["status"] == "active")

```

---

### Metadata query

```

GET /users?qb=QB.created_by().eq("admin")

```

---

### Date filter

```

GET /orders?qb=QB.created_time() >= datetime(2024,1,1)

```

---

### Complex query

```

GET /users?qb=QB.all(
QB["age"] > 18,
QB.any(
QB["status"] == "active",
QB["status"] == "trial"
)
)

```

---

# Summary

Key points:

- `QB` is the **recommended query interface**
- data fields use `QB["field"]`
- metadata fields use `QB.resource_id()` etc.
- conditions can be combined with `&`, `|`, `QB.all()`, `QB.any()`
- queries are passed via the `qb` HTTP parameter

---

See also:
- [Search indexing](search-indexing.md)