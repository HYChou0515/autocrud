"""Deprecated alias for the ``specstar`` package.

This module installs an ``importlib`` meta-path finder that redirects every
``autocrud`` and ``autocrud.*`` import to the matching ``specstar`` /
``specstar.*`` module, emitting a ``DeprecationWarning`` once per import path.

It exists only as a migration runway for users on ``autocrud<=0.9.x``. The
real codebase lives at https://github.com/HYChou0515/specstar.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
import warnings

_PREFIX = "autocrud"
_TARGET = "specstar"
_MIGRATION_URL = (
    "https://github.com/HYChou0515/specstar/blob/master/MIGRATION.md"
)
_warned: set[str] = set()


class _SpecstarRedirector(importlib.abc.MetaPathFinder):
    """Redirect ``autocrud[.X]`` imports to ``specstar[.X]`` with a warning."""

    def find_spec(self, name, path, target=None):  # type: ignore[override]
        if name != _PREFIX and not name.startswith(_PREFIX + "."):
            return None
        new_name = _TARGET + name[len(_PREFIX):]
        if name not in _warned:
            warnings.warn(
                f"`{name}` is deprecated. Use `{new_name}` instead. "
                f"See {_MIGRATION_URL}",
                DeprecationWarning,
                stacklevel=2,
            )
            _warned.add(name)
        return importlib.util.find_spec(new_name)


sys.meta_path.insert(0, _SpecstarRedirector())

# Re-export the public surface so ``from autocrud import <symbol>`` keeps
# working without forcing a submodule import path.
from specstar import *  # noqa: E402, F401, F403
