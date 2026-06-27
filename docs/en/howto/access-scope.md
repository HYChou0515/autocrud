# Read/write access scope (row-level security)

`access_scope` is a per-model predicate that SpecStar **ANDs into every
request-originated read**, and enforces as a **precondition for every
request-originated write**. It gives you row-level security — "which resources
exist *for this user*" — at a single choke point, without per-route wiring.

```python
spec.add_model(
    Doc,
    indexed_fields=[("visibility", str), ("owner", str), ("readers", list)],
    access_scope=lambda user: (
        (QB["visibility"] == "public")
        | (QB["owner"] == user)
        | QB["readers"].contains_any([user])
    ),
)
```

The callable is `user -> ConditionBuilder | None | UNRESTRICTED`:

| Return value          | Meaning                                                        |
| --------------------- | ------------------------------------------------------------- |
| a `ConditionBuilder`  | restrict to rows matching the predicate                       |
| `None`                | **deny all** (fail-closed) — list/count empty, every GET 404  |
| `UNRESTRICTED`        | no restriction (admins / privileged callers)                  |

```python
from specstar import UNRESTRICTED

def scope_for(user: str):
    if user == "admin":
        return UNRESTRICTED          # sees everything
    if user == "banned":
        return None                  # sees nothing
    return (QB["visibility"] == "public") | (QB["owner"] == user)
```

`UNRESTRICTED` is the single, greppable "see everything" path — there is no
implicit global-admin bypass.

## What it gates

**Reads** — `access_scope` ANDs into `list` / `search` / `count` **and** every
single-resource GET variant (`/{id}`, `/data`, `/full`, `/meta`,
`/revision-info`, `/revision-list`, and the resource-scoped
`/{id}/blobs/{file_id}`):

- list/search/count return only in-scope rows, filtered **at the storage layer**.
- a single GET of an out-of-scope resource returns **404** — its existence is
  hidden, uniformly with list filtering, never a 403.

**Writes** — `access_scope` is a **necessary precondition** for every
request-originated write that targets an existing resource by id: `update`,
`modify`, `patch`, `delete`, `permanently_delete`, `switch`, and `restore`
(plus the batch delete/restore endpoints, which only touch in-scope rows). A
write to an out-of-scope resource raises not-found (**404**) *before* the
permission checker runs, so writes never leak existence either.

`create` is **not** gated — there is no existing resource to be out of scope of.

## access_scope is visibility, not authorization

`access_scope` answers *"does this row exist for this caller?"* (→ 404). It is
**not** a replacement for a [permission checker](permissions.md), which answers
*"is this caller allowed to perform this action?"* (→ 403). They compose:

1. `access_scope` is evaluated **first**. Out of scope → 404, and the checker
   never runs (no existence leak via a 403).
2. For an in-scope resource, the `permission_checker` still runs and may deny
   the write with a 403.

So a typical resource is locked down with **both**: a broad read predicate
(public *or* owner *or* shared) plus a narrower write checker (e.g.
`owner_self`, which only the owner passes). Setting only `access_scope` makes a
resource invisible *and* unwritable to outsiders, but in-scope callers can still
write it unless a checker says otherwise.

## Opt-in and internal calls

Scoping is applied only when a read/write is entered with
`apply_access_scope=True`:

- **Generated routes opt in for you.** Every built-in read route and every
  built-in write route enters `using(..., apply_access_scope=True)`.
- **Custom routes must opt in explicitly.** If you write your own route that
  reads or mutates resources on behalf of the request user, wrap the call:

  ```python
  with resource_manager.using(user=current_user, apply_access_scope=True):
      resource_manager.update(resource_id, data)
  ```

  A custom route that forgets this is **not** scoped — treat it like any other
  place you must apply authorization by hand.
- **Internal `ResourceManager` calls stay unscoped.** Async jobs, constraints,
  restore/migration machinery, and any other trusted internal read or write see
  everything — exactly as before. A model with no `access_scope` configured pays
  nothing.

## Fields must be indexed

A scope predicate may only reference `ResourceMeta` attributes or configured
indexed fields. A predicate over an unindexed field **always raises**
(`UnindexedQueryError`), regardless of the model's `on_unindexed_query` setting —
a silently-dropped condition would *widen* visibility, a security hole. Register
every field your predicate touches:

```python
spec.add_model(
    Doc,
    indexed_fields=[("visibility", str), ("owner", str), ("readers", list)],
    access_scope=scope_for,
)
```

For list-membership ACLs (`readers.contains_any([user])`), the list field must be
registered as a list-typed indexed field so it compiles to true element
membership rather than a substring match.

## Caveat: the bare blob endpoint

The bare `GET /blobs/{file_id}` endpoint is a global, content-addressed blob
download with **no resource context**, so `access_scope` (a per-resource
predicate) cannot apply to it. The resource-scoped
`GET /{model}/{id}/blobs/{file_id}` route *is* scoped. If you need row-level
security on blob content, do not expose the bare endpoint, or gate it yourself.

## Related pages

- [Permissions](permissions.md) — action-based authorization (the 403 side).
- [Query Builder](query-builder.md) — building the predicate.
- [Routes generation](routes.md)
