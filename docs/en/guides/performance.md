
# Performance notes

Performance depends on storage backend, indexing choices, payload size, and query patterns.

## Storage backend

SpecStar uses a storage factory to create a per-model storage instance:

- **Memory storage**: suitable for development / small datasets; fastest, but not persistent.
- **Disk storage** (or other persistent backends): suitable for production; performance depends on IO.

If you store blobs, blob store behavior may also depend on the chosen storage factory.

## Indexing

Use `add_model(indexed_fields=...)` to index frequently queried fields.

Trade-offs:
- Indexing improves query speed and filtering capability.
- Indexing increases write/update cost and storage size.

## Listing & pagination

For large datasets:
- use paginated list endpoints
- avoid returning huge payloads in one request
- prefer querying fields that are indexed

## Updating many rows at once

Pushing one change across many rows — mirroring a collection's visibility onto
every document in it, say — is not a job for a loop of `update()`. Each
iteration costs a meta read, a payload read, an encode and two writes, and on a
remote backend every one of those is a round-trip. Use `patch_many` instead:

```python
result = rm.patch_many(
    (QB["collection_id"] == collection_id).build(),
    MergePatch({"visibility": "public"}),
)
print(result.patched, result.unchanged, result.conflicts, result.failures)
```

You describe the fields that change and never touch the data. That is what
makes the batching possible: once the read belongs to SpecStar, it can fetch a
whole batch in one query (`octet_length` + one `SELECT` on Postgres, concurrent
`head_object` + `GET` on S3) and write the batch back through `save_*_bulk`.
Handing the manager `(resource_id, full_data)` pairs instead would keep the read
on your side, one round-trip at a time.

What it does **not** change:

- **Events, and therefore permission checks, still fire per row.** Write ACLs
  are per-row policies; authorizing a batch is not the same as authorizing its
  rows.
- **A row whose revision moved since it was selected is reported as a
  conflict**, not overwritten — a patch rewrites the whole body, so writing
  anyway would discard a concurrent edit entirely. Re-run to pick conflicts up.
- **A no-op patch creates no revision**, so re-running a fan-out is cheap and
  you do not need to pre-filter rows that already hold the target value.

Failures are collected rather than raised, so one unwritable row does not
strand the rest; they come back in `result.failures` as `(resource_id, reason)`.

### Memory

`max_bytes` (default 256 MiB) caps how much row data is held at once. The
budget is in bytes rather than a row count on purpose: row size varies by
orders of magnitude between models, so a batch size that suits a flat derived
table will exhaust memory on documents that carry their whole extracted text.
Rows are read in budget-sized batches; a row larger than the entire budget is
still processed, on its own.

### Watch the count

`patch_many` patches exactly what the query selects — **including its
`limit`**, which carries a process-wide default that a deployment can configure
via `SPECSTAR_DEFAULT_QUERY_LIMIT`. `result.total` reports how many rows were
selected, so compare it against what you expected rather than assuming the
fan-out covered everything.

## Backup / restore

`dump()` and `load()` are streaming-based (msgpack archive). For large backups:
- run as offline maintenance jobs
- expect throughput to be limited by storage IO and payload size