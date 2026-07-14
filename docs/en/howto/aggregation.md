# Aggregation and grouping

SpecStar can group resources by a field and reduce each group with aggregates —
counts, sums, min/max, averages — pushed down to the storage engine as a real
`GROUP BY`, and (since v0.11.x) **ordered and paginated at the group level** so a
consumer can page through the *distinct groups* themselves.

Use it when you want *"how many chunks per document"*, *"newest member per
cluster"*, or *"the top 20 buckets by size, one page at a time"* without
streaming every matching row into Python.

!!! note "Experimental surface"
    The entry point is `ResourceManager.exp_aggregate_by` (the `exp_` prefix
    marks it experimental — the signature may still adjust before it stabilises
    as `aggregate_by`). `exp_count_groups` follows the same convention.

---

## When to use it

- counting or summarising rows **per group** (a `GROUP BY` in SQL terms)
- annotating each parent with a **reduction over its children** in another
  resource (*"this doc's chunk count"*)
- paging a **grouped list** by an aggregate value or the group key — e.g. a
  review queue grouped by concept, newest first, 20 concepts per page

For row-level filtering, sorting, and pagination of individual resources, use the
[Query Builder](/specstar/howto/query-builder) with `search_resources` instead —
that pages *rows*, this pages *groups*.

---

## Self-aggregates

Import the aggregates from the top-level package and group with a `QB` field:

```python
from specstar import QB, Count, Sum, Min, Max, Avg

rows = manager.exp_aggregate_by(
    QB["source_doc_id"],                 # group by an indexed data field
    {"chunks": Count(), "bytes": Sum(QB["size"])},
    query=(QB["status"] == "ready").build(),   # optional row filter (WHERE)
)
for r in rows:
    print(r.key, r.chunks, r.bytes)      # one GroupRow per distinct source_doc_id
```

| Aggregate | Reduces | Empty / all-`None` group |
|-----------|---------|--------------------------|
| `Count()` | rows in the group | `0` |
| `Sum(field)` | numeric field (`None`-skipping) | `None` |
| `Min(field)` / `Max(field)` | comparable field (`None`-skipping) | `None` |
| `Avg(field)` | numeric field → `float` (`None`-skipping) | `None` |

`Sum`/`Avg` raise `TypeError` on a non-numeric value; `Min`/`Max` use Python `<`
ordering, so the field's values must be mutually comparable (numbers, datetimes,
or strings). A missing / unindexed group-by value collects under `key=None`.

You can group by a **`ResourceMeta` attribute** too — `QB.created_by()`,
`QB.created_time()`, etc. — and aggregate over one:

```python
rows = manager.exp_aggregate_by(
    QB.created_by(),
    {"n": Count(), "latest": Max(QB.created_time())},
)
```

### The result: `GroupRow`

Each row is a `GroupRow` with:

- `.key` — the group-by value (`None` when the value was missing)
- each named aggregate as **both** an attribute and an item, so
  `row.chunks` and `row["chunks"]` are equivalent — a dict comprehension like
  `{r.key: r.chunks for r in rows}` just works
- `.resource` — populated only in the cross-RM parent mode below (otherwise
  `None`, because a group can span many rows)

---

## Foreign aggregates: parent rows with children stats

To annotate each parent with a reduction over a **different** resource's rows,
pass a `ForeignAggregate(child_rm, link_field, aggregate)` — `link_field` is the
field on the child that holds the parent's `resource_id`:

```python
from specstar import QB, Count, ForeignAggregate

rows = doc_manager.exp_aggregate_by(
    QB.resource_id(),                    # one group == one parent row
    {"chunks": ForeignAggregate(chunk_manager, QB["source_doc_id"], Count())},
)
for r in rows:
    print(r.resource.data.name, r.chunks)   # .resource is the parent row
```

Grouping by `QB.resource_id()` is the **parent-row mode**: each group is exactly
one row of *this* manager, so `GroupRow.resource` carries that row's
`SearchedResource` — read `r.resource.data.<field>` alongside the children stat.
The foreign reduction runs as one extra query scoped to just the keys the page
surfaces, not one query per parent.

---

## Ordering and paginating the groups

Pass `order_by`, `limit`, and `offset` to page through the **distinct groups**
(separate from the row-level `query.limit/offset`, which an aggregate ignores):

```python
page = manager.exp_aggregate_by(
    QB["bucket"],
    {"n": Count(), "hi": Max(QB["size"])},
    order_by="-hi",      # order by the 'hi' aggregate, descending
    offset=0, limit=20,  # first 20 groups
)
```

- **`order_by`** — an aggregate **result-name** (a key of the `aggregates` dict)
  or the sentinel **`"key"`** (the group key). It uses the same `"-name"` /
  `"+name"` convention as `Query.sort()`: ascending by default, `-` for
  descending. A target that is neither an aggregate name nor `"key"` raises
  `ValueError`; a negative `offset`/`limit` raises.
- **Stable pages** — the group key is always the ascending secondary sort, so
  two groups with equal `order_by` values never straddle a page boundary or
  reappear on the next page.
- **NULLs last** — a `None` order-value **and** a `None` group key always sort
  last, regardless of direction.

### Pager total

`exp_count_groups` returns the number of distinct groups the same `by` + `query`
would produce — the total a pager needs, independent of any `limit`/`offset`:

```python
total = manager.exp_count_groups(QB["bucket"], query=q)
```

### Worked example: a paged, grouped queue

Group members by a cluster key, order each concept by its newest member, and
return one page of concepts plus the total — then load just that page's members:

```python
from specstar import QB, Count, Max

q = (
    (QB["state"] == "active")
    & (QB["kind"] << ["proposal", "question"])
).build()

page = member_manager.exp_aggregate_by(
    QB["cluster_key"],
    {"n": Count(), "latest": Max(QB.created_time())},
    query=q,
    order_by="-latest",          # newest concept first
    offset=offset, limit=size,
)
total = member_manager.exp_count_groups(QB["cluster_key"], query=q)

keys = [r.key for r in page]     # this page's concepts
members = member_manager.search_resources((QB["cluster_key"] << keys).build())
```

Each page returns a fixed number of groups no matter how many rows exist — the
load stays constant as the dataset grows.

---

## Push-down and performance

The value reduction (`Count`/`Sum`/`Min`/`Max`/`Avg`) is pushed down to any meta
store that implements `IMetaWithAgg` (SQLite and PostgreSQL today) as a real
engine `GROUP BY`; other backends fall back to an in-process reduction that
returns **identical** results.

The group-level `ORDER BY … LIMIT … OFFSET` is pushed down as well — so a page
scans only the groups it returns — when **both** hold:

- the store advertises group paging (SQLite and PostgreSQL do), and
- the `order_by` target is **engine-orderable**: the group key, or a
  single-column self-aggregate (`Count`, `Sum`, `Min`, `Max`, including
  `Min`/`Max` over a `ResourceMeta` datetime column).

Ordering by `Avg` (internally a `Sum` + a `Count`) or by a `ForeignAggregate`
falls back to ordering the fully-materialised groups in Python — still correct,
still identical across backends, just not `O(page)` at the engine. NULLs-last is
spelled with a `(expr IS NULL)` prefix rather than native `NULLS LAST`, so
SQLite, PostgreSQL, and the in-process reference agree byte-for-byte.

!!! note "Not a counter cache"
    A pushed-down `GROUP BY` is scan-fast, not `O(1)`. For a genuinely hot,
    high-fan-out count, maintain a denormalised counter on write instead.

---

## Gotchas

- **Group-by must be a `QB` field.** Pass `QB["field"]` (indexed data) or a
  meta accessor like `QB.created_by()` — a plain string raises `TypeError`.
- **Index the fields you group / aggregate on.** An unindexed data field is
  treated as `None` (and warns, or raises under the `error`
  `on_unindexed_query` policy) — every row then collapses into the `key=None`
  group. Add it to `indexed_fields`.
- **`order_by`/`limit` page groups, not rows.** The row-level `query.limit` /
  `query.offset` are ignored for an aggregate — an aggregate spans the whole
  filtered set.
- **`.resource` is only set in parent-row mode** (`by=QB.resource_id()`); for
  any other `by` it is `None`.

See the [Query Builder reference](/specstar/reference/query-builder) for the full
field and operator surface, and the
[Python API reference](/specstar/reference/python_api) for the generated
`exp_aggregate_by` / aggregate signatures.
