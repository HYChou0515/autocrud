# Prune old revisions

SpecStar keeps every change as a new revision (see
[Data versioning](/specstar/quickstart/data-versioning)). That history is the
point — but on long-lived resources it also accumulates storage you may no
longer need. `prune_revisions` hard-deletes selected historical revisions to
reclaim space, while **always keeping the current revision**.

> **Python API only (for now).** `prune_revisions` is a `ResourceManager`
> method. There is no generated HTTP route and no permission gate for it yet —
> call it from trusted server-side code (a maintenance job, a CLI command, a
> scheduled task). It *does* emit a `prune` event, so any
> [event handler](/specstar/howto/event-handlers) you have registered observes
> it like any other action.

---

## The API

```python
pruned_ids = mgr.prune_revisions(
    resource_id,
    *,
    keep_last_n=...,   # int >= 1, optional
    before=...,        # aware datetime, optional
    user=...,          # who performed the prune (for the event), optional
    now=...,           # clock for the event, optional
)
```

- Returns `list[str]` — the revision ids that were pruned (empty when nothing
  matched).
- Raises `ValueError` if you pass **neither** `keep_last_n` **nor** `before`, or
  if `keep_last_n < 1`.
- Raises `ResourceIDNotFoundError` if the resource id does not exist.
- Works on soft-deleted resources too.

You must supply at least one of `keep_last_n` or `before`; there is no
"prune everything" mode, because the current revision is never prunable.

---

## What gets kept

Two knobs select what to **keep**; everything else is pruned.

`keep_last_n` keeps the *n* most important revisions, ranked from most to least
important by:

1. **Lineal first** — revisions on the current revision's ancestry chain (follow
   `parent_revision_id` from the current revision back to the root) rank above
   collateral branches. Collateral branches appear when you `switch()` to an old
   revision and then edit, forking the history.
2. **Newer first** — within the same lineage, more recently created wins.

The current revision is always lineal and the newest of its own line, so it is
always rank 1 and never pruned. (A deterministic tie-break on the revision
sequence number keeps `keep_last_n` stable when several revisions share a
timestamp: the full sort key is `(is_lineal, created_time, sequence)`, ranked
descending.)

`before` keeps every revision created **at or after** the given timestamp and
prunes those created strictly before it.

> **`total_revision_count` never decreases.** It seeds new revision ids and must
> stay monotonic, so pruning leaves it untouched. The *live* number of revisions
> is `len(mgr.list_revisions(resource_id))`; `mgr.get_meta(resource_id).total_revision_count`
> is the running total ever created, which keeps climbing.

---

## Example

Take a `Config` resource that has been edited many times. We stamp explicit
timestamps so the `before` example is reproducible.

```python
from datetime import datetime, timedelta, timezone

import msgspec
from fastapi import FastAPI

from specstar import spec, Schema


class Config(msgspec.Struct):
    value: str


app = FastAPI()
spec.configure(default_user="ops", default_now=lambda: datetime.now(timezone.utc))
spec.add_model(Schema(Config, "v1"))
spec.apply(app)

mgr = spec.get_resource_manager(Config)

# 8 revisions, one per day: rev 1 (oldest) ... rev 8 (current).
base = datetime(2025, 1, 1, tzinfo=timezone.utc)
info = mgr.create(Config(value="v0"), now=base)
rid = info.resource_id
for i in range(1, 8):
    mgr.update(rid, Config(value=f"v{i}"), now=base + timedelta(days=i))

print(len(mgr.list_revisions(rid)))            # 8  -> live revision count
print(mgr.get_meta(rid).total_revision_count)  # 8  -> running total
```

### Keep the last N

```python
pruned = mgr.prune_revisions(rid, keep_last_n=3)

print(len(pruned))                             # 5  -> the 5 oldest were pruned
print(len(mgr.list_revisions(rid)))            # 3  -> current + 2 newest survive
print(mgr.get_meta(rid).total_revision_count)  # 8  -> unchanged (monotonic)
```

The current revision is still readable, untouched:

```python
print(mgr.get(rid).data.value)                 # "v7"
```

### Prune everything older than a date

On a fresh 8-revision resource:

```python
cutoff = base + timedelta(days=4)              # keep rev 5..8, prune rev 1..4
pruned = mgr.prune_revisions(rid, before=cutoff)

print(len(pruned))                             # 4
print(len(mgr.list_revisions(rid)))            # 4
```

### Combine both knobs (conservative union)

When you pass both, the kept sets **union**: a revision survives if *either*
knob would keep it. Equivalently, a revision is pruned only when it is *both*
beyond `keep_last_n` *and* older than `before`.

```python
# keep_last_n=2 alone would prune 6 (keep rev 7, 8).
# before=cutoff alone would prune 4 (keep rev 5..8).
# Union keeps rev 5..8 -> prunes only 4. rev 5, 6 survive because `before`
# keeps them even though keep_last_n=2 would have dropped them.
pruned = mgr.prune_revisions(rid, keep_last_n=2, before=base + timedelta(days=4))

print(len(pruned))                             # 4
```

---

## Blob interplay

If your resources carry [binary data](/specstar/howto/binary-data), pruning a
revision **decrements** the reference count of the blobs that revision pointed
at — it never deletes blob contents directly. A blob is only reclaimed once no
surviving revision references it, and reclamation happens in a separate
garbage-collection pass you run yourself with `spec.gc(...)`.

So the storage from pruned revision payloads is freed immediately, but the
underlying blob bytes are freed on the next GC. See
[Binary data → Blob lifecycle and garbage collection](/specstar/howto/binary-data)
for how and when to run `gc()`.

---

## Related pages

- [Data versioning](/specstar/quickstart/data-versioning) — how revisions are
  created and read in the first place
- [Binary data](/specstar/howto/binary-data) — blob storage and the `gc()` pass
  that reclaims unreferenced blobs
- [Event handlers](/specstar/howto/event-handlers) — observe the `prune` event
