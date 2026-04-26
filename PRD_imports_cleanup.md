# PRD: Clean up `autocrud.events` / `autocrud.types` import cycle and stop re-exporting moved symbols

## Problem Statement

Maintainers of AutoCRUD currently work around a circular import between `autocrud.events` and `autocrud.types`. The workarounds — a PEP-562 `__getattr__` shim at the bottom of `autocrud.events`, two `noqa: E402` re-import blocks in `autocrud.types`, and ~89 unused-import warnings flagged by ruff in `types.py` alone — exist only because `autocrud.types` is being used as a re-export facade for symbols whose canonical home is now elsewhere.

The cost of this is paid every time someone:

- Opens `autocrud/types.py` or `autocrud/events.py` and tries to understand which module owns which symbol.
- Adds a new event-related type and has to decide whether it lives in `types.py` or `events.py`.
- Tries to satisfy `make check` without disabling lint rules.
- Reads a test like `from autocrud.types import BeforeCreate` and incorrectly concludes that `types.py` defines `BeforeCreate`.

There is also a parallel symptom: a small group of tests reach into private (`_underscore`) helpers in production modules. Those tests pin internal mechanics that should be free to change, and they were written against private symbols only because the public surface did not (yet) cover the behaviour they wanted to test.

## Solution

1. **Break the cycle.** Move `IEventHandler` from `autocrud.types` into `autocrud.events`, and move the `do(...)` builder + `SimpleEventHandler` from `autocrud.resource_manager.events` into `autocrud.events`. After the move, `autocrud.events` becomes a deep, self-contained module that owns every event-shaped symbol; `autocrud.types` imports *from* `autocrud.events` and `autocrud.query_types` only what it genuinely needs internally, and never imports back.
2. **Delete the re-export facade.** `autocrud.types` stops being a public re-export point for moved symbols. Every caller in production code and tests is updated to import from the canonical owner (`autocrud.events`, `autocrud.query_types`, or `autocrud.errors`).
3. **Pin the new public surface with assertions.** `tests/test_public_api_exports.py` is extended so each curated namespace explicitly enumerates the import paths AutoCRUD users are expected to rely on, and the now-removed paths fail loudly.
4. **Rewrite tests that depend on private symbols** to exercise the same behaviour through the public surface, so future internal refactors do not break them.

After the cleanup, the rule for AutoCRUD is uniform: **import from the canonical owner; the public surface is exactly what `__all__` lists in each curated namespace.**

## User Stories

1. As an AutoCRUD maintainer, I want `autocrud.events` to define every event-related symbol it exposes, so that I can read one file end-to-end and understand the entire event subsystem.
2. As an AutoCRUD maintainer, I want `autocrud.types` to contain only domain types that are genuinely defined there, so that opening that file no longer surprises me with re-exports from other modules.
3. As an AutoCRUD maintainer, I want `make check` to pass without `noqa: E402` and without 89 ruff F401 warnings, so that lint output reflects real problems and not architectural debt.
4. As an AutoCRUD maintainer, I want there to be no circular import between `events.py` and `types.py`, so that I do not need to think about module-initialisation order when adding a new symbol.
5. As an AutoCRUD maintainer, I want the PEP-562 `__getattr__` shim to be deleted, so that lookups of `autocrud.events.IEventHandler` resolve through normal attribute access and IDE go-to-definition works.
6. As a contributor adding a new event-context struct, I want a single, obvious place to add it — namely `autocrud.events` — so that I do not have to remember to also re-export from `autocrud.types`.
7. As a library user wiring up event handlers, I want `from autocrud.events import IEventHandler, EventContext, do, BeforeCreate` to be the documented and guaranteed import path, so that I can copy a snippet from the docs without trial and error.
8. As a library user writing a search query, I want `from autocrud.query_types import ResourceMetaSearchQuery, FieldTransform` to be the canonical path, so that there is exactly one place to look for query types.
9. As a library user catching exceptions, I want `from autocrud.errors import …` to remain the curated public namespace for exceptions, so that I do not need to know which internal module raises a given error.
10. As a contributor writing a test, I want a single import rule — "import from the canonical owner" — so that I never have to choose between two paths that resolve to the same symbol.
11. As a contributor reading test failures after a refactor, I want `tests/test_public_api_exports.py` to fail clearly when a public path I removed is still being depended on, so that I learn about the breakage in one place rather than across dozens of unrelated tests.
12. As a release manager, I want the public-API contract tests to assert that *removed* import paths now raise `ImportError`, so that backward-incompatible changes show up loudly in CI rather than silently appearing to work.
13. As an AutoCRUD maintainer renaming an internal helper, I want no test to break because it imported `_underscore`-prefixed symbols, so that I am free to refactor private mechanics.
14. As an AutoCRUD maintainer reading `autocrud/resource_manager/events.py`, I want it either to be deleted or to have a clear, narrow purpose, so that the module name does not collide with `autocrud.events` for new contributors.
15. As an AutoCRUD maintainer auditing imports, I want every `from autocrud.types import X` in production code to import a symbol whose canonical owner is `types.py`, so that I can grep for unexpected cross-module dependencies confidently.
16. As an AutoCRUD maintainer, I want the move to leave runtime behaviour identical — same handler dispatch, same event payloads, same exception semantics — so that this PRD ships as a pure refactor with no observable change.
17. As a downstream user of the package, I want `autocrud.__init__` and the curated subpackage namespaces (`autocrud.events`, `autocrud.errors`, `autocrud.permission`, `autocrud.query_types`, `autocrud.resource_manager`) to remain the only paths I need, so that I am not forced to update many imports myself.
18. As a contributor reading the docs/skills, I want examples to use the canonical import paths consistently, so that I am never told to import the same symbol from two different places in two different sections.
19. As a contributor running `pytest tests/test_public_api_exports.py`, I want that file alone to be a sufficient check that the public surface is correctly wired, so that quick smoke tests are possible without running the full suite.
20. As an AutoCRUD maintainer adding a new public symbol, I want a clear convention — define it in its canonical module, list it in that module's `__all__`, and add it to `test_public_api_exports.py` — so that the public surface stays explicit and tested.
21. As an AutoCRUD maintainer reviewing a PR, I want CI to fail when a new test imports a private (`_underscore`) symbol, so that the cleanup does not silently regress over time. (Optional follow-up; see Out of Scope.)
22. As an AutoCRUD maintainer, I want each previously-private symbol that a test depended on to either remain private (with the test rewritten through the public surface) or be promoted to a public symbol with a deliberate name and `__all__` entry, so that no symbol is half-private-half-public.

## Implementation Decisions

### Module ownership

- **`autocrud.events` becomes the canonical owner of every event-shaped symbol.** It owns: every `Before/After/OnSuccess/OnFailure*` context struct, the `EventContext` union, the `EventContextProto` / `HasData` / `HasResourceId` / `HasDataAndResourceId` / `HasRevisionId` / `HasInfo` protocol family, the `IEventHandler` ABC (moved here from `autocrud.types`), and the `do(...)` builder + `SimpleEventHandler` (moved here from `autocrud.resource_manager.events`). The module exposes an explicit `__all__`.
- **`autocrud.types` becomes a pure domain-types module.** It only imports from `autocrud.events` and `autocrud.query_types` what it itself uses (currently `EventContext` for the `PermissionContext` alias, and `ResourceMetaSearchQuery` for `IResourceManager` method signatures). It exports no event-context structs and no query types. It also drops genuinely unused imports flagged by ruff (`os`, `warnings`, `Protocol`, `runtime_checkable`, `defstruct`).
- **`autocrud.query_types` is the canonical owner of search/query/sort types.** No structural change required.
- **`autocrud.resource_manager.events` is deleted** once `do(...)` and `SimpleEventHandler` move to `autocrud.events`. Internal callers re-target their imports.
- **`autocrud.errors`, `autocrud.permission`, `autocrud.resource_manager` (subpackage `__init__`)** continue to be curated namespaces backed by explicit `__all__`. Their content does not change in this PRD.

### Cycle-break direction

- After the move, the import direction is one-way: `autocrud.events` → `autocrud.types` → `autocrud.query_types`. There must be no edge from `autocrud.types` back to `autocrud.events`.

### Caller updates

- Production code that imports moved symbols via `autocrud.types` is updated to import from the canonical owner. Affected production modules (non-exhaustive): `crud/core.py`, `crud/ref_manager.py`, `resource_manager/core.py`, `resource_manager/constraint_handler.py`, `permission/acl.py`, `permission/rbac.py`, several `resource_manager/meta_store/*` backends.
- Tests that import moved symbols via `autocrud.types` are updated the same way. Affected test files (non-exhaustive): `test_event_handlers.py`, `test_unique_event_handler.py`, `test_query_builder.py`, `test_bulk_load.py`, `test_constraint_handler.py`, `test_storage_factory_kebab_table_name.py`, `test_operation_context.py`, `test_s3_storage_factory.py`, `test_public_api_exports.py`, `meta_store/test_s3_meta_store.py`, `permission/test_permission_system.py`, `routes/test_global_crud.py`.
- `PermissionContext` remains a use-site alias of `EventContext`. It stays in `autocrud.types` because `IPermissionChecker` lives there.

### Public surface contract

- Each curated namespace gets (or keeps) an explicit `__all__`.
- `tests/test_public_api_exports.py` gains assertions that:
  - Positive: each curated public path (`autocrud.events`, `autocrud.query_types`, `autocrud.errors`, `autocrud.permission`, `autocrud.resource_manager`, package root `autocrud`) exposes the documented symbols.
  - Negative: removed paths fail. Specifically, `from autocrud.types import ResourceMetaSearchQuery` (and the other moved symbols) raises `ImportError`. The PEP-562 `__getattr__` no longer exists, so lookups of removed names on `autocrud.events` would only succeed if defined directly — which is the intended behaviour.

### Backward compatibility

- This refactor breaks deprecated import paths intentionally. No compat shims, no `DeprecationWarning` layer, no `__getattr__` fallbacks. `autocrud.__init__` and the curated namespaces continue to expose the same symbols as before, so users who already follow the documented import paths are unaffected.
- `autocrud.resource_manager.events` is removed as a public-importable module. Tests and any internal callers must update to `autocrud.events`. (No external consumer is expected to have been importing from `autocrud.resource_manager.events` directly, since it was never part of any curated namespace.)

### Private-symbol test rewrites

- Six tests currently import `_underscore` helpers. Each is rewritten to exercise the same behaviour through the public surface:
  - `_evaluate_trivalent` — exercise via a `search` route or `ResourceManager.search_resources` test that produces the same trivalent outcomes.
  - `_read_default_query_limit` — exercise via the search route's actual default-limit behaviour, monkeypatching the relevant environment variable.
  - `_needs_pruning` — exercise via a `ResourceManager.modify()` test that triggers the partial-pruning code path end-to-end.
  - `_clean_action_name` — exercise via the registered route name produced by an async-create action, since route naming is the observable consequence.
  - `_convert_annotation` — exercise via `pydantic_to_struct` / `pydantic_to_validator` on a struct that contains the annotation shapes the helper handles.
  - `_sanitize_schema_names` — exercise via a generated OpenAPI schema test that asserts the resulting `components.schemas` keys.
- After the rewrite, no test imports any `_underscore`-prefixed symbol from `autocrud.*`.

### Run-time behaviour

- This PRD is a pure refactor. There is no change to handler-dispatch order, event payload shape, exception semantics, route generation, schema migration, or storage. The acceptance bar is that `make ci` (lint + tests + coverage) passes with the same coverage profile as before.

## Testing Decisions

### What makes a good test in this PRD

A good test in this PRD asserts **observable external behaviour** — which import paths exist, which symbols are reachable from a documented namespace, and which behaviours hold from the user's point of view (e.g. "calling `ResourceManager.modify()` on a partial input prunes the right fields"). It does **not** assert internal mechanics like "function `_needs_pruning` returns True for this dict". When the implementation moves a helper or renames it, a good test still passes.

### Modules under test

- **Public-API surface tests** (`tests/test_public_api_exports.py`): the canonical list of import paths AutoCRUD supports. Treated as a contract.
- **Event subsystem tests** (`tests/test_event_handlers.py`, `tests/test_unique_event_handler.py`): handler dispatch, builder API, event-context payloads. Their imports change from `autocrud.types` and `autocrud.resource_manager.events` to `autocrud.events`.
- **Rewritten behaviour tests** for the six private-symbol cases listed above. Each test moves to exercise the public surface that depends on the now-private helper.
- **Existing integration tests** (`tests/test_autocrud.py`, `tests/routes/*`, `tests/permission/*`, `tests/meta_store/*`) — no behavioural changes, only import-path updates.

### Prior art for the new tests

- The pattern in `tests/test_public_api_exports.py` already demonstrates the contract-test style: small functions like `test_events_namespace_exposes_builder_api()` and `test_errors_namespace_exposes_public_exception_families()`. New assertions follow the same shape.
- The negative assertion `with pytest.raises(ImportError): from autocrud import ResourceOps` already exists in `test_root_does_not_export_resource_ops`. The same pattern is used to pin removed paths.
- The behaviour-level tests for `ResourceManager.modify()`, async-action route names, and OpenAPI schema generation already exist in their respective test files and are followed as templates for the rewrites.

## Out of Scope

- **Adding a CI lint rule that blocks future `_underscore` imports from tests.** This is a useful follow-up but requires a custom ruff rule or a `conftest.py`-level check; it is intentionally separated from the refactor itself so this PRD stays a single, reviewable diff.
- **Reorganising `autocrud.types` further.** The exception classes, `IResourceManager` interface, ref machinery, and other domain types stay where they are even though some of them could plausibly live in their own modules. This PRD limits "moves" to the cycle-causing event/query types.
- **Rewriting `autocrud/__init__.py`'s `__all__`.** The package root continues to expose the same symbols. Curated subpackage namespaces are updated, but the package-level top imports are unchanged.
- **Documentation rewrites beyond import-path fixes.** Docstrings, MkDocs pages, and skill files are updated only where they explicitly reference an import path that is changing. Conceptual rewrites are deferred.
- **Type-checker configuration changes.** No changes to `pyright`, `mypy`, or `ruff` configuration are needed; the cleanup makes existing checks happy rather than relaxing them.
- **Web generator and frontend code.** The TypeScript generator and React app do not reference Python import paths and are not touched.

## Further Notes

- After the refactor, `autocrud.events` becomes a *deep* module: a single file owns the entire event subsystem (context types, handler interface, builder), with a small, stable public API. This is the unit-of-change for any future work on event semantics.
- The cleanup expects roughly: ~2 production files heavily edited (`events.py`, `types.py`), ~10 production files lightly edited (import-path renames), ~12 test files lightly edited (import-path renames), 6 test files moderately edited (private-symbol rewrites), and 1 test file (`test_public_api_exports.py`) extended with new contract assertions.
- A future, separate PRD may consider promoting some `_underscore` helpers to public symbols if their behaviour is genuinely useful to library users. None of the six helpers identified in this PRD obviously qualifies — they are all internal mechanics — so the default is to keep them private and test through the surface.
- Running `make ci` to green is the single acceptance criterion. No new manual QA is required because the refactor changes no run-time behaviour.
