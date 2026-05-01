# autocrud (deprecated)

This package has been renamed to **[specstar](https://pypi.org/project/specstar/)**.
Install the new name:

```bash
pip install specstar
```

The `autocrud` package on PyPI is now a thin shim that redirects every
`autocrud.*` import to the matching `specstar.*` module with a
`DeprecationWarning`. No new releases of `autocrud` will be published beyond
`0.10.0` — please migrate.

See the [migration guide](https://github.com/HYChou0515/specstar/blob/master/MIGRATION.md)
for details.
