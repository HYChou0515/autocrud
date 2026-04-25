# Query Builder Reference

This page is the single lookup reference for the Query Builder in AutoCRUD.

Use it when you already understand the basic idea and need the exact method names, operator shortcuts, metadata helpers, or pagination behavior.

For task-oriented examples, start with the [Query Builder guide](/autocrud/howto/query-builder). For the bigger mental model, see the [Query system overview](/autocrud/concepts/query-system).

---

## Core building blocks

The Query Builder is organized around four practical pieces:

- `QB` — the main entry point for data fields, metadata accessors, and grouped logic
- `Field` — returned by `QB["field"]` or helpers such as `QB.created_time()`
- `ConditionBuilder` — the chainable object produced after comparisons and helper calls
- `Query` — the pagination and sorting layer used by methods such as `sort()`, `limit()`, `offset()`, `page()`, and `first()`

In practice, most users only need to remember two patterns:

```python
QB["status"].eq("active")
QB.created_time().last_n_days(7).sort("-created_time").page(1, 20)
```

---

## Operator shortcuts

These operators are supported in normal Python usage and are also mirrored by the safe HTTP `qb` parser where applicable.

| Syntax | Meaning | Equivalent helper |
|------|---------|-------------------|
| `QB["age"] == 18` | equality | `QB["age"].eq(18)` |
| `QB["age"] != 18` | inequality | `QB["age"].ne(18)` |
| `QB["age"] > 18` | greater than | `QB["age"].gt(18)` |
| `QB["age"] >= 18` | greater than or equal | `QB["age"].gte(18)` |
| `QB["age"] < 18` | less than | `QB["age"].lt(18)` |
| `QB["age"] <= 18` | less than or equal | `QB["age"].lte(18)` |
| `(cond1) & (cond2)` | logical AND | `QB.all(cond1, cond2)` |
| `(cond1) | (cond2)` | logical OR | `QB.any(cond1, cond2)` |
| `~cond` | logical NOT | invert the current condition |
| `~QB["field"]` | falsy-value shortcut | `QB["field"].is_falsy()` |
| `QB["tags"] << ["a", "b"]` | list membership | `QB["tags"].in_(["a", "b"])` |
| `QB["title"] >> "urgent"` | contains check | `QB["title"].contains("urgent")` |
| `QB["code"] % r"^[A-Z]+$"` | regex match | `QB["code"].regex(...)` |

> In HTTP URLs, prefer the clearer helper style such as `QB["title"].contains("urgent")`, especially if the expression will be encoded by a client.

---

## Field access patterns

### Data fields

Use bracket notation for indexed data fields:

```python
QB["name"]
QB["profile.email"]
QB["field-with-dash"]
QB["class"]
```

### Resource metadata fields

Use helper accessors when you want to filter or sort on built-in resource metadata:

| Helper | Filters/sorts on |
|--------|------------------|
| `QB.resource_id()` | resource identifier |
| `QB.current_revision_id()` | current revision identifier |
| `QB.created_time()` | creation timestamp |
| `QB.updated_time()` | last update timestamp |
| `QB.created_by()` | creator |
| `QB.updated_by()` | last updater |
| `QB.is_deleted()` | soft-delete flag |
| `QB.schema_version()` | schema version |
| `QB.total_revision_count()` | revision count |

Example:

```python
QB.resource_id().starts_with("task-")
QB.updated_by().ne("guest")
QB.is_deleted().is_false()
```

---

## Comparison and range helpers

| Method | Purpose | Example |
|--------|---------|---------|
| `eq(value)` | equals | `QB["status"].eq("active")` |
| `ne(value)` | not equals | `QB["status"].ne("archived")` |
| `gt(value)` | greater than | `QB["score"].gt(80)` |
| `gte(value)` | greater than or equal | `QB["score"].gte(80)` |
| `lt(value)` | less than | `QB["score"].lt(80)` |
| `lte(value)` | less than or equal | `QB["score"].lte(80)` |
| `between(min_val, max_val)` | inclusive range | `QB["price"].between(100, 500)` |
| `in_range(min_val, max_val)` | alias for `between()` | `QB["age"].in_range(18, 65)` |

---

## String matching helpers

| Method | Purpose | Example |
|--------|---------|---------|
| `contains(value)` | substring or containment match | `QB["title"].contains("urgent")` |
| `starts_with(value)` | prefix match | `QB["email"].starts_with("admin")` |
| `ends_with(value)` | suffix match | `QB["email"].ends_with("@example.com")` |
| `regex(pattern)` | regular expression | `QB["code"].regex(r"^[A-Z]{3}")` |
| `match(pattern)` | alias for `regex()` | `QB["email"].match(r".*@gmail\.com$")` |
| `like(pattern)` | SQL-like `%` / `_` matching | `QB["name"].like("Alice%")` |
| `icontains(value)` | case-insensitive contains | `QB["title"].icontains("urgent")` |
| `istarts_with(value)` | case-insensitive prefix | `QB["name"].istarts_with("admin")` |
| `iends_with(value)` | case-insensitive suffix | `QB["email"].iends_with("@gmail.com")` |
| `not_contains(value)` | negated contains | `QB["description"].not_contains("spam")` |
| `not_starts_with(value)` | negated prefix | `QB["filename"].not_starts_with("tmp")` |
| `not_ends_with(value)` | negated suffix | `QB["filename"].not_ends_with(".tmp")` |

---

## List, null, and value helpers

| Method | Purpose | Example |
|--------|---------|---------|
| `in_(values)` | value is in a list | `QB["status"].in_(["draft", "review"])` |
| `not_in(values)` | value is not in a list | `QB["role"].not_in(["guest"])` |
| `one_of(values)` | alias for `in_()` | `QB["owner"].one_of(["alice", "bob"])` |
| `is_null(value=True)` | null check | `QB["deleted_at"].is_null()` |
| `is_not_null()` | not-null check | `QB["email"].is_not_null()` |
| `has_value()` | alias for `is_not_null()` | `QB["nickname"].has_value()` |
| `is_empty()` | empty string or null | `QB["description"].is_empty()` |
| `is_blank()` | empty, null, or whitespace-only | `QB["name"].is_blank()` |
| `is_true()` | equals `True` | `QB["verified"].is_true()` |
| `is_false()` | equals `False` | `QB["disabled"].is_false()` |
| `is_truthy()` | meaningful non-empty value | `QB["status"].is_truthy()` |
| `is_falsy()` | null, empty, false, or zero | `QB["optional_field"].is_falsy()` |
| `exists(value=True)` | exists operator | `QB["extra"].exists()` |
| `isna(value=True)` | missing / NA-style check | `QB["score"].isna()` |

---

## Grouping, sorting, and pagination helpers

### Grouping helpers

| Method | Purpose | Example |
|--------|---------|---------|
| `filter(*conditions)` | AND additional conditions | `QB["age"].gt(18).filter(QB["status"].eq("active"))` |
| `exclude(*conditions)` | AND with negated conditions | `QB["status"].eq("active").exclude(QB["role"].eq("guest"))` |
| `and_(other)` | alias for `&` | `cond1.and_(cond2)` |
| `or_(other)` | alias for `|` | `cond1.or_(cond2)` |
| `QB.all(*conditions)` | explicit AND group | `QB.all(cond1, cond2, cond3)` |
| `QB.any(*conditions)` | explicit OR group | `QB.any(cond1, cond2)` |

### Sorting and pagination helpers

| Method | Purpose | Example |
|--------|---------|---------|
| `sort(*sorts)` | add one or more sort rules | `QB["status"].eq("active").sort("-created_time", "+name")` |
| `order_by(*sorts)` | alias for `sort()` | `query.order_by("-created_time")` |
| `limit(n)` | maximum result count | `QB["status"].eq("active").limit(10)` |
| `offset(n)` | skip first `n` results | `QB["status"].eq("active").offset(20)` |
| `page(page, size=20)` | 1-based pagination helper | `QB["status"].eq("active").page(2, 10)` |
| `first()` | set the limit to 1 | `QB["status"].eq("active").first()` |
| `build()` | produce `ResourceMetaSearchQuery` | `query.build()` |

### Sort direction helpers

| Helper | Meaning |
|--------|---------|
| `QB["name"].asc()` | ascending sort object |
| `QB["created_time"].desc()` | descending sort object |

---

## Date and time helpers

These helpers operate on date-like fields and metadata timestamps.

| Method | Purpose | Example |
|--------|---------|---------|
| `today(tz=None)` | current day range | `QB.created_time().today()` |
| `yesterday(tz=None)` | previous day range | `QB.created_time().yesterday()` |
| `this_week(tz=None, week_start=0)` | current week range | `QB.updated_time().this_week()` |
| `this_month(tz=None)` | current month range | `QB.created_time().this_month()` |
| `this_year(tz=None)` | current year range | `QB.created_time().this_year()` |
| `last_n_days(n, tz=None)` | values from the last N days | `QB.created_time().last_n_days(30)` |

The `tz` parameter accepts:

- `None` for the local timezone
- an integer offset such as `8` for UTC+8
- a string offset such as `"+8"`
- a real `tzinfo` object in normal Python code

Example:

```python
QB.created_time().today(8)
QB.created_time().this_week(week_start=6)
QB.updated_time().last_n_days(14, "+8")
```

> If you are manually writing an HTTP URL, remember that `+` should be URL-encoded. Using `8` is often simpler than writing `"+8"` by hand.

---

## Transform helpers

`length()` creates a virtual field based on the length of the current field value.

Use it for string length, list size, or object key-count style checks:

```python
QB["tags"].length() > 3
QB["name"].length().between(5, 20)
QB["items"].length() == 0
```

---

## Important behavior notes

- QB works best with indexed resource fields and built-in metadata fields.
- In HTTP requests, do not combine `qb` with `data_conditions`, `conditions`, `sorts`, or time-range/user filter parameters (`created_time_start`, `created_time_end`, `updated_time_start`, `updated_time_end`, `created_bys`, `updated_bys`). Those conflicts return HTTP 422.
- **`is_deleted` is the one exception**: it may be combined with `qb`. The server ANDs it into the QB conditions. Because Swagger sends `is_deleted=false` by default, QB expressions work in Swagger without any extra workaround.
- Invalid or unsupported QB expressions return HTTP 400.
- URL `limit` and `offset` override pagination values defined inside the QB expression itself.
- `QB["user.email"]` refers to the stored field path used by the search layer. It should not be read as a promise of arbitrary deep object traversal beyond what is indexed.

---

## Related pages

- [Query Builder guide](/autocrud/howto/query-builder)
- [Query system overview](/autocrud/concepts/query-system)
- [Search indexing](/autocrud/concepts/search-indexing)
- [HTTP errors](/autocrud/howto/http-errors)

---

## Auto-generated API details

For the full docstring-backed API surface, see the generated module reference below.

::: autocrud.query
