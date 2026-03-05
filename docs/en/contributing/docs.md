# Documentation rules

## Public API boundary
Only symbols exported from `autocrud/__init__.py` are considered public API.

## Docstring style
Use Google-style docstrings with these required sections:

- One-line summary
- Args / Returns
- Raises (only if actually raised)
- Examples (at least one)

## No endpoint enumerations in docstrings
Do not list generated endpoints in docstrings. Put route behavior under `docs/howto/routes.md`.