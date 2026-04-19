# Documentation rules

This page summarizes the conventions for writing and updating AutoCRUD documentation.

## Public API boundary
Only symbols exported from `autocrud/__init__.py` are considered public API for onboarding-oriented imports.

For exceptions, prefer documenting and importing them from `autocrud.errors`.

## Where docs live

- English docs live under `docs/en/`
- navigation is defined in `mkdocs.yml`
- task-oriented behavior belongs in the how-to pages rather than in docstrings

## Docstring style
Use Google-style docstrings with these sections when they apply:

- One-line summary
- Args / Returns
- Raises, only if actually raised
- Examples, ideally adapted from real usage or tests

## Writing rules

- Do not invent endpoints, options, or behaviors that are not present in the codebase
- Prefer concise, practical examples over exhaustive prose
- Keep docs and implementation aligned when behavior changes
- Use the docs to explain usage and guarantees, not every internal detail

## No endpoint enumerations in docstrings
Do not list generated endpoints in docstrings. Put route behavior under `docs/howto/routes.md` and related guide pages.

## Verification before submitting
Before merging doc changes, build the site locally:

```bash
uv run mkdocs build
```

A docs change is only considered finished once the site still builds successfully.