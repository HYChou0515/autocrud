# Changelog

All notable changes to SpecStar (formerly `autocrud`).

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Added

- **`ResourceManager.get(..., include_deleted=True)`** reads a revision of a
  soft-deleted resource instead of raising `ResourceIsDeletedError`, mirroring
  `get_meta(include_deleted=...)`. Defaults to `False`, so existing behavior is
  unchanged. Fixes the Data Versioning quickstart, which showed inspecting an
  old revision after a soft delete.
- **RFC 7386 JSON Merge Patch support.** `PATCH` now accepts a partial-update
  object (e.g. `{"qty": 50}`) in addition to RFC 6902 JSON Patch (the op array).
  The same endpoint disambiguates by explicit `Content-Type`
  (`application/merge-patch+json` vs `application/json-patch+json`) or, for a
  generic `application/json`, by body shape (object → merge, array → ops).
  Previously a partial object returned `400`; this is additive (error → success).
  Programmatically, `ResourceManager.patch()` and `.modify()` now accept a
  `MergePatch(...)` (new, exported from `specstar`) alongside a `JsonPatch`,
  mirroring the RFC 6902 path — the HTTP route delegates to these.
- **`ResourceManager.iter_all(query=None, *, batch_size=1000)`** yields every
  matching resource by paging internally, so a full scan can never silently
  truncate (unlike a `search`/list bounded by `limit`).
- **List truncation signals on `GET /{model}`**: an always-present `X-Has-More`
  header (computed cheaply via a limit+1 probe) and an opt-in `X-Total-Count`
  header (`?with_total=true`). The response body is unchanged (a bare array).
- **`SpecStarWarning`** advisory category, emitted once at `apply()` when
  permissive defaults are left in place: `forbid_unknown_fields` off, or no
  `SPECSTAR_DEFAULT_QUERY_LIMIT` configured. Silence via standard `warnings`
  filters.
- **Production Hardening guide** section consolidating the above into one
  copy-pasteable baseline (`docs/en/guides/from-demo-to-production.md`).

### Changed

- **Programmatic writes without an operation context now fall back to
  `anonymous` + `now()` (non-strict mode).** `ResourceManager.create()` /
  `update()` / `modify()` / etc. called without a `using()` context and with no
  configured `default_user` / `default_now` previously leaked a raw
  `LookupError`; they now record `created_by="anonymous"` and the current UTC
  time — the same values an unauthenticated HTTP request produces. Set
  `strict_operation_context=True` to restore the hard failure (a friendly
  `MissingOperationContextError`).
- **`add_model(default_user=...)` now propagates to HTTP audit fields.**
  Resources created over HTTP for that model record the per-model
  `created_by` / `updated_by` instead of `"anonymous"`. Precedence: a real
  `get_user` (authentication) > per-model `default_user` > global
  `configure(default_user=...)` > `"anonymous"`. Only affects apps that set a
  per-model `default_user` (others are unchanged).
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
