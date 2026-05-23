"""Skip every test in this directory if the optional GraphQL extra is missing.

The GraphQL route templates require ``strawberry-graphql`` (install via
``pip install specstar[graphql]``). On a stock dev environment without that
extra, importing the route template module raises at import time, which
turns into a *collection* error and breaks the whole test run.

``collect_ignore_glob`` short-circuits collection of this directory's test
files when the extra is not installed, so the fast CI job can run pytest
unconditionally without manually deselecting the directory.
"""

try:
    import strawberry  # noqa: F401
except ImportError:
    collect_ignore_glob = ["test_*.py"]
