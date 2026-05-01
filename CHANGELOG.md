# Changelog

All notable changes to SpecStar (formerly `autocrud`).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
- **Logo**: text and mark variants in `branding/`.

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
