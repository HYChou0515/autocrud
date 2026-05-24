# Query Builder

SpecStar includes a high-level query builder for searching indexed resource fields and resource metadata.

Use it when you want expressive filtering logic in Python or when you want your HTTP `qb` expressions to mirror the same mental model.

If you need a complete method-by-method lookup, see the [Query Builder reference](/specstar/reference/query-builder).

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
from specstar import QB

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

List endpoints are paginated by default. The startup default comes from the SPECSTAR_DEFAULT_QUERY_LIMIT environment variable, and you can still pass a different limit per request.

The server parses the expression with a safe AST parser.

> ### Heads up — bare query params on list endpoints are **silently ignored**
>
> `GET /task?name=Alice` returns *all* tasks, not the ones whose `name` is
> `Alice`. SpecStar's list endpoints **do not** auto-bind unknown query
> parameters to data fields — filtering has to go through one of:
>
> * `?qb=…` *(recommended)* — the safe expression DSL on this page,
> * `?data_conditions=…` — JSON array of structured conditions,
> * `?conditions=…` — meta-level conditions,
> * the dedicated metadata params (`is_deleted`, `created_time_start`, …).
>
> The looseness is a deliberate 0.x trade-off: in a versioned system,
> resources can sit at different schema versions, so strict
> validation of arbitrary `?field=value` filters against "the current
> schema" would either reject legitimate old data or require a full
> "which fields are queryable at which versions" matrix. That work is
> out of scope for 0.x.
>
> If you want a louder failure for typos, opt in per-request with
> `?strict_filters=true` *(coming after 0.11; see issue tracker)* —
> until then, **always go through `qb` / `conditions` for filtering**.

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
QB.current_revision_id().eq("rev-123")
QB.created_by().eq("admin")
QB.is_deleted().is_false()
QB.total_revision_count() > 3
```

All built-in metadata accessors are filterable and sortable, including `resource_id`, `current_revision_id`, `created_time`, `updated_time`, `created_by`, `updated_by`, `is_deleted`, `schema_version`, and `total_revision_count`.

### Revision mirror fields

SpecStar stores a denormalized snapshot of the **current revision's** key attributes directly in `ResourceMeta`. These can be filtered and sorted without any extra revision reads:

```python
QB.rev_status().eq("draft")                     # only resources with a draft current revision
QB.rev_status().eq("stable")                    # only stable
QB.rev_created_by().one_of(["alice", "bob"])    # current revision created by alice or bob
QB.rev_updated_by().ne("guest")                 # current revision not last touched by guest
QB.rev_created_time().last_n_days(7)            # current revision created in the past week
QB.rev_updated_time().this_month()              # current revision updated this month
```

These fields are kept in sync by SpecStar on every `create()`, `update()`, `modify()`, and `switch()` call.

---

## Low-level alternative

If you need fully explicit structured queries, you can still build `ResourceMetaSearchQuery` objects manually:

```python
from specstar.types import (
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

## Listing everything (no query)

`search_resources`, `count_resources`, `list_resources`, and `iter_all` all
accept **no argument**, which matches every resource — equivalent to passing
`QB.all()` (or an empty `ResourceMetaSearchQuery()`):

```python
manager.search_resources()       # every resource's meta
manager.count_resources()        # total count
manager.list_resources()         # every resource, with data
for meta in manager.iter_all():  # paged full scan
    ...
```

Prefer `iter_all()` when you genuinely want *all* rows — it pages internally, so
a forgotten `limit` can't silently truncate the result.

---

## Important limitations

- queries only work reliably on metadata fields and indexed fields
- if `qb` is used in HTTP requests, do not combine it with `data_conditions`, `conditions`, `sorts`, time-range / user filter params (`created_time_start`, `created_time_end`, `updated_time_start`, `updated_time_end`, `created_bys`, `updated_bys`), or revision filter params (`rev_statuses`, `rev_created_bys`, `rev_updated_bys`, `rev_created_time_start`, `rev_created_time_end`, `rev_updated_time_start`, `rev_updated_time_end`); conflicting requests return HTTP 422
- **`is_deleted` is the one exception**: it may be combined with `qb`. The server ANDs it into the QB conditions automatically. Swagger always sends `is_deleted=false` by default, so QB expressions work in Swagger out of the box.
- invalid or unsupported QB expressions return HTTP 400
- URL `limit` and `offset` override pagination values defined inside the QB expression
- for metadata filtering in QB mode (time ranges, creator filters, revision filters, etc.), include them directly in the expression — for example `QB.created_time().last_n_days(7)`, `QB.created_by().eq("alice")`, or `QB.rev_status().eq("draft")`

### QB error responses at a glance

| Situation | HTTP | What to do |
|-----------|------|------------|
| malformed or unsupported QB expression | 400 | fix the expression itself |
| `qb` combined with JSON conditions, sorts, or time-range/user filter params | 422 | choose either QB mode or individual query parameters |

For the shared route-level error mapping, see the HTTP error reference page.

---

## Good practices

- index fields that you plan to search frequently
- start with small filters and expand only when needed
- use `QB.all()` and `QB.any()` for nested grouped logic
- prefer QB for readability and JSON conditions for machine-generated requests

---

## Related pages

- [Query Builder reference](/specstar/reference/query-builder)
- [Query system](/specstar/concepts/query-system)
- [Search indexing](/specstar/concepts/search-indexing)
- [Routes generation](/specstar/howto/routes)
- [Troubleshooting](/specstar/howto/troubleshooting)
