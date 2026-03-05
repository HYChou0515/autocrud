
# Performance notes

Performance depends on storage backend, indexing choices, payload size, and query patterns.

## Storage backend

AutoCRUD uses a storage factory to create a per-model storage instance:

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

## Backup / restore

`dump()` and `load()` are streaming-based (msgpack archive). For large backups:
- run as offline maintenance jobs
- expect throughput to be limited by storage IO and payload size