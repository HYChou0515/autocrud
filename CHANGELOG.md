# Changelog

All notable changes to SpecStar (formerly `autocrud`).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---
## [0.11.8] — 2026-06-10


### Fixed

- Bounded ESTALE retry on disk stores (#352)
- Atomic writes + TOCTOU translation on disk stores (#352)

## [0.11.7] — 2026-06-09


### Added

- Exp_aggregate_by — group-by + Count aggregate (v1, experimental)
- Exp_aggregate_by — add Sum / Min / Max / Avg
- Exp_aggregate_by handles cross-RM (one method, ForeignAggregate)
- Field.source — make QB[] vs QB.foo() a real dispatch (aggregate API breaks str)


### Fixed

- Snapshot before iterating to survive concurrent writes
- Make create() crash-safe — atomic meta commit + typed not-found (#340)

## [0.11.6] — 2026-06-07


### Added

- Lease-based distributed lock (#342 #2)
- Partition_key serialization + idempotent enqueue (#342 #3/#4)
- Optimistic concurrency (#342 part 1) — expected_revision_id, if_not_exists
- Expected_etag CAS — detect concurrent in-place modify()
- Wire CAS through If-Match / If-None-Match + ETag (#342 part 2)

## [0.11.5] — 2026-05-26


### Added

- Default_is_deleted option for programmatic list/count/iter


### Fixed

- Reject path/URL-unsafe custom resource_id

## [0.11.4] — 2026-05-24


### Added

- GET only-* returns + default_get_returns, raw-body import, partial nudge


### Documentation

- Note id/timestamps/author/version are built-in metadata
- Fix verified doc bugs (event-handler imports, resource_id, kebab)

## [0.11.3] — 2026-05-24


### Added

- Configurable on_decode_error policy (skip/error/raw)
- On_unindexed_query policy (warn/error) for non-indexed filters
- No-arg search_resources / count_resources (match-all, = QB.all())


### Documentation

- Audit-user how-to + list-truncation & schema-divergence notes
- Surface that on_delete defaults to dangling


### Fixed

- Warn when count/list diverge on undecodable rows
- Apply registered migrations lazily on the read path
- Accept do(...) builders inside event_handlers=[...]
- Discoverable get_resource_manager error + no-arg list_resources

## [0.11.2] — 2026-05-24


### Added

- Production-hardening pass — audit fields, PATCH 7386, safety nets
- Programmatic writes without a context fall back to anonymous + now()


## [0.11.1] — 2026-05-23

### Added

- **`ResourceManager.get(..., include_deleted=True)`** reads a revision of a
  soft-deleted resource instead of raising `ResourceIsDeletedError`, mirroring
  `get_meta(include_deleted=...)`. Defaults to `False`, so existing behavior is
  unchanged. Fixes the Data Versioning quickstart, which showed inspecting an
  old revision after a soft delete.

### Changed

- **BREAKING — `resource_id` is rejected in request bodies (was silently
  dropped).** Sending `resource_id` in a `POST` / `PUT` body, or targeting
  `/resource_id` in a `PATCH` op, now returns **`422`** instead of `200`.
  Previously the key was silently ignored and the server-generated id was
  returned anyway, so clients believed they had set an id they hadn't.
  `resource_id` is server-generated at creation and immutable thereafter; to
  customise id generation pass `id_generator=` to `add_model(...)`. The guard
  steps aside only when the resource Struct legitimately declares its own
  `resource_id` field.

---

## [0.10.0] — 2026-05-01

The package is renamed from `autocrud` to **`specstar`**. No public method
signatures or behaviors changed; this is a brand and identifier rename.

### Renamed

- **PyPI distribution**: `autocrud` → **`specstar`**.
- **Top-level Python package**: `autocrud` → **`specstar`**.
- **Class**: `AutoCRUD` → **`SpecStar`**. Importable as
  `from specstar.crud.core import SpecStar` or `from specstar import SpecStar`.
- **Global instance**: the singleton exported from the top-level package was
  renamed `crud` → **`spec`**. Use `from specstar import spec`.
- **Warning class**: `AutoCRUDWarning` → **`SpecStarWarning`**.
- **Environment variable**: `AUTOCRUD_DEFAULT_QUERY_LIMIT` →
  **`SPECSTAR_DEFAULT_QUERY_LIMIT`**. The legacy name still works during
  the migration window with a one-shot `DeprecationWarning`.
- **Repository / docs URL**: `github.com/HYChou0515/autocrud` →
  `github.com/HYChou0515/specstar`. The old URL redirects.

### Added

- **Deprecation shim**: a new `autocrud==0.10.0` is published on PyPI as a
  thin wrapper around `specstar==0.10.0`. It installs an `importlib`
  meta-path finder that redirects every `autocrud[.X]` import to the
  matching `specstar[.X]` module at runtime, emitting a `DeprecationWarning`
  once per import path. This is the last release of `autocrud`; future
  releases ship as `specstar` only.
- **Migration guide**: see [MIGRATION.md](MIGRATION.md) for the find /
  replace table and shim details.
- **Logo**: text and mark variants in `docs/assets/`.

### Fixed

- **GraphQL resolvers** silently swallowed exceptions when `ResourceMeta`
  carried newly-added `rev_*` fields, when `indexed_data` was `UNSET`, or
  when `RevisionInfo.uid` (a `UUID`) was passed to a `str`-typed strawberry
  field. Resolvers now project only the fields the GraphQL type declares,
  map `UNSET → None`, and stringify UUIDs.
- **`SpecStar.apply()`** returned `app.router` (the FastAPI internal
  `APIRouter`) instead of the documented "supplied `router` if any, else
  `app`". The return value now matches the docstring.

### Pre-existing on `autocrud<=0.9.0`

The two `Fixed` items above were latent bugs on the 0.9.0 line. If you're
upgrading directly from `autocrud==0.9.0` you'll get the fixes
transparently — no code change required.

---

## [0.9.0] — 2026-04-29

Last release under the `autocrud` name. Breaking changes are documented in
detail in [docs/en/guides/upgrade-0.9.md](docs/en/guides/upgrade-0.9.md).

### Removed

- `PostgreSQLStorageFactory` and `PostgreSQLDiskS3StorageFactory` (deprecated
  with a runtime warning since 0.8). Replace with `PostgreSQLS3StorageFactory`
  or compose the meta / resource / blob stores directly.
- `specstar.permission.basic` (deprecated since 0.8). Use the unified APIs
  in `specstar.permission`.

### Changed

- `IResourceStore` now requires `save_many()` and `dump_all_revisions()` on
  every backend. Custom stores must implement both.
- `dump()` returns a generator of `(meta, revisions)` tuples rather than a
  flat record stream. Callers that built a list need to flatten or pivot.
- `IResourceManager` subclasses must implement `load_records_bulk()`.
- `start_consume(block=False)` returns the worker handle instead of `None`.

### Added

- **`ResourceMeta` carries the current-revision fields** (`rev_status`,
  `rev_created_by`, `rev_updated_by`, `rev_created_time`, `rev_updated_time`).
  Run `ResourceManager.backfill_revision_meta()` once after deploying to
  populate them on resources created on earlier versions; until you do, the
  fields are `UNSET`. (#274)

---

## Earlier releases

For releases before 0.9.0, see the
[GitHub Releases page](https://github.com/HYChou0515/specstar/releases) and
the per-version notes embedded in
[docs/en/guides/](docs/en/guides/).
