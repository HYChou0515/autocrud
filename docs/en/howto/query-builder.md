# Query Builder

AutoCRUD includes a high-level query builder for searching indexed resource fields and resource metadata.

Use it when you want expressive filtering logic in Python or when you want your HTTP `qb` expressions to mirror the same mental model.

---

## When to use it

The query builder is useful for:

- filtering lists by field values
- combining multiple conditions with AND, OR, and NOT
- building reusable search logic in services or tests
- keeping search code readable instead of hand-writing JSON filter payloads

---

## Basic Python usage

```python
from autocrud.query import QB

query = (
    QB["status"].eq("active")
    .filter(QB["priority"] >= 3)
    .exclude(QB["archived"].eq(True))
    .sort("-created_time")
    .page(1, 20)
)

results = manager.search_resources(query)
```

`QB[...]` returns a field-aware builder object, so comparison operators and helper methods can be chained naturally.

---

## HTTP usage

The same ideas can be passed to the API through the `qb` query parameter:

```text
GET /tasks?qb=(QB["status"] == "active") & (QB["priority"] >= 3)
GET /tasks?qb=QB["owner"].one_of(["alice", "bob"])
GET /tasks?qb=QB.created_time().last_n_days(7)
```

List endpoints are paginated by default. The startup default comes from the AUTOCRUD_DEFAULT_QUERY_LIMIT environment variable, and you can still pass a different limit per request.

The server parses the expression with a safe AST parser.

---

## Common patterns

### Simple comparisons

```python
QB["age"] > 18
QB["status"].eq("active")
QB["score"].between(80, 100)
```

### String matching

```python
QB["name"].contains("ali")
QB["email"].ends_with("@example.com")
QB["title"].icontains("urgent")
QB["code"].regex(r"^[A-Z]{3}")
```

### List membership

```python
QB["status"].in_(["draft", "review"])
QB["role"].not_in(["guest"])
QB["owner"].one_of(["alice", "bob"])
```

### Null and value checks

```python
QB["deleted_at"].is_null()
QB["email"].is_not_null()
QB["nickname"].is_blank()
QB["profile"].has_value()
```

### Date helpers

```python
QB.created_time().today()
QB.updated_time().this_week()
QB.created_time().last_n_days(30)
```

### Sorting and pagination

```python
QB["status"].eq("active").sort("-created_time", "+name")
QB["status"].eq("active").limit(10).offset(20)
QB["status"].eq("active").page(2, 10)
QB["status"].eq("active").first()
```

---

## Metadata accessors

Use metadata helper methods when the filter targets resource metadata instead of indexed data.

```python
QB.resource_id().starts_with("task-")
QB.revision_id().eq("rev-123")
QB.created_by().eq("admin")
QB.is_deleted().is_false()
QB.total_revision_count() > 3
```

For built-in metadata sorting, use `resource_id`, `created_time`, or `updated_time`.

---

## Low-level alternative

If you need fully explicit structured queries, you can still build `ResourceMetaSearchQuery` objects manually:

```python
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)

query = ResourceMetaSearchQuery(
    conditions=[
        DataSearchCondition(
            field_path="status",
            operator=DataSearchOperator.equals,
            value="open",
        ),
        DataSearchCondition(
            field_path="priority",
            operator=DataSearchOperator.greater_than_or_equal,
            value=3,
        ),
    ],
    limit=20,
)

results = manager.search_resources(query)
```

This is useful for generated clients or integrations that prefer explicit JSON-like structures.

---

## Important limitations

- queries only work reliably on metadata fields and indexed fields
- if `qb` is used in HTTP requests, do not combine it with `data_conditions`, `conditions`, or `sorts`
- URL `limit` and `offset` override pagination values defined inside the QB expression
- if you need delete-status filtering in QB mode, include it directly in the expression, for example `QB.is_deleted().is_false()`

---

## Good practices

- index fields that you plan to search frequently
- start with small filters and expand only when needed
- use `QB.all()` and `QB.any()` for nested grouped logic
- prefer QB for readability and JSON conditions for machine-generated requests

---

## Related pages

- [Query system](/autocrud/concepts/query-system)
- [Search indexing](/autocrud/concepts/search-indexing)
- [Routes generation](/autocrud/howto/routes)
- [Troubleshooting](/autocrud/howto/troubleshooting)
