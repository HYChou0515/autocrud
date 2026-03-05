# Search and indexing

AutoCRUD provides query + search without forcing developers to touch a database.

Search is based on a simple model:

- All queries run against **resource-level metadata** (`ResourceMeta`)
- Plus an extracted, searchable projection of data: **`indexed_data`**

No revision scanning is performed.

## What is `indexed_data`?

`indexed_data` is a dictionary stored in `ResourceMeta`:

```python
indexed_data: dict[str, Any]
```

It is extracted from the resource data (`T`) during:

* `create()`
* `update()`
* `modify()` (when data changes)

The main purpose:

* enable fast filtering / sorting without decoding or scanning revisions
* keep search focused on “the current version” (HEAD) of a resource

## Data types

`indexed_data` supports **any JSON value** (as stored by your encoding):

* scalars: string / number / bool / null
* objects / arrays

Storage backends may impose practical constraints depending on implementation, but the semantic contract is “any JSON”.

## Flattened (shallow) keys

AutoCRUD treats indexed fields as **flattened keys**, e.g.:

* `"user.email"` is stored directly as a key in `indexed_data`

So query comparison is shallow:

* no nested traversal is required at query time
* the index builder already produced the flattened key

This matches the Query Builder behavior:

* `QB["user.email"]` targets the key `"user.email"` in `indexed_data`

## What does search query over?

A search query only considers:

1. `ResourceMeta` fields (built-in)
2. `indexed_data` fields (extracted from `data`)

It does **not**:

* scan revision history
* search inside old revisions
* scan raw payload bytes

This makes performance predictable and aligns with the “current state” semantics of most APIs.

## Sorting

Sorting is supported on:

* `ResourceMeta` fields (e.g. `created_time`, `updated_time`)
* `indexed_data` fields (e.g. `"user.email"`, `"score"`)

## Query Builder (recommended)

AutoCRUD provides a Query Builder (“QB”) that makes filtering readable and safe.

Examples (conceptual):

```python
QB.resource_id().eq("...")
QB.created_time().last_n_days(7)
QB.is_deleted() == False
QB["user.email"].eq("a@b.com")
QB.all(QB["age"] > 18, QB["status"] == "active")
QB.any(QB["tier"] == "gold", QB["tier"] == "platinum")
```

The Query Builder is the recommended way to build complex conditions, because:

* it is expressive
* it avoids hand-writing condition JSON
* it matches the behavior of `indexed_data` flattening

## API surface

In HTTP APIs, search/list endpoints generally accept:

* `qb=` (recommended)
* or structured JSON parameters such as:

  * `conditions=...`
  * `data_conditions=...`
  * `sorts=...`
* plus pagination (`limit`, `offset`)
* plus response shaping (`returns=...`, `partial=...`)

See also:

* `concepts/query-system.md`
* `howto/routes.md`