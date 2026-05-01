# Upgrading to 0.10 (`autocrud` → `specstar`)

Version 0.10.0 renames the package from `autocrud` to **`specstar`**. No
public method signatures or behaviors changed; this is a brand and
identifier rename.

The full migration walkthrough — including a find / replace table, the
deprecation-shim path, and verification steps — lives in the
[MIGRATION.md](https://github.com/HYChou0515/specstar/blob/master/MIGRATION.md)
guide at the repository root.

## Quick checklist

- [ ] `pip install -U specstar` (or pin `autocrud>=0.10.0` for the shim)
- [ ] Replace `from autocrud` → `from specstar` everywhere
- [ ] Replace `AutoCRUD` → `SpecStar` and `AutoCRUDWarning` → `SpecStarWarning`
- [ ] Rename the global instance reference `crud` → `spec`
- [ ] Replace env var `AUTOCRUD_DEFAULT_QUERY_LIMIT` →
      `SPECSTAR_DEFAULT_QUERY_LIMIT`
- [ ] Re-run any Starter Wizard projects to regenerate `main.py` (or
      hand-edit the import line)

## Backward compatibility

- `autocrud==0.10.0` ships as a **deprecation shim** that redirects every
  `autocrud[.X]` import to `specstar[.X]` at runtime, with a
  `DeprecationWarning` per import path. Existing code keeps working without
  edits.
- The legacy `AUTOCRUD_DEFAULT_QUERY_LIMIT` env var is still read with a
  `DeprecationWarning` if `SPECSTAR_DEFAULT_QUERY_LIMIT` is unset.

The shim is a migration runway, not a long-term home — `autocrud==0.10.0`
is the **last release** under that name.

## See also

- [MIGRATION.md](https://github.com/HYChou0515/specstar/blob/master/MIGRATION.md)
  — the full guide
- [Schema migration](../howto/migrations.md) — for *data* migrations
  (evolving your `msgspec.Struct` shapes); unrelated to the package rename
