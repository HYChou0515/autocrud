"""Deprecated alias for the ``specstar`` package.

This module installs an ``importlib`` meta-path finder that redirects every
``autocrud`` and ``autocrud.*`` import to the matching ``specstar`` /
``specstar.*`` module, emitting a ``DeprecationWarning`` once per import path.

It exists only as a migration runway for users on ``autocrud<=0.9.x``. The
real codebase lives at https://github.com/HYChou0515/specstar.
"""

from __future__ import annotations

import importlib
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


def _warn_once(name: str) -> None:
    if name in _warned:
        return
    _warned.add(name)
    new_name = _TARGET + name[len(_PREFIX):]
    warnings.warn(
        f"`{name}` is deprecated. Use `{new_name}` instead. "
        f"See {_MIGRATION_URL}",
        DeprecationWarning,
        stacklevel=3,
    )


class _SpecstarRedirector(importlib.abc.MetaPathFinder):
    """Redirect ``autocrud[.X]`` imports to ``specstar[.X]`` with a warning.

    Matches ``autocrud`` itself plus any submodule, eagerly imports the
    corresponding ``specstar`` module, and aliases it in ``sys.modules`` under
    the requested ``autocrud`` name so subsequent attribute access and
    submodule imports work transparently.
    """

    def find_spec(self, name, path, target=None):  # type: ignore[override]
        if name != _PREFIX and not name.startswith(_PREFIX + "."):
            return None
        target_name = _TARGET + name[len(_PREFIX):]
        _warn_once(name)
        # Import the real module (loads specstar.X into sys.modules).
        real_module = importlib.import_module(target_name)
        # Alias under the autocrud name so future lookups are O(1).
        sys.modules[name] = real_module
        # Return a spec that points at the already-loaded module so the
        # import machinery does not try to load it a second time. We
        # preserve `is_package` semantics by copying `__path__` if present.
        loader = _AlreadyLoadedLoader()
        is_pkg = hasattr(real_module, "__path__")
        spec = importlib.util.spec_from_loader(name, loader, is_package=is_pkg)
        if is_pkg:
            spec.submodule_search_locations = list(real_module.__path__)
        return spec


class _AlreadyLoadedLoader(importlib.abc.Loader):
    """Loader for modules pre-populated in ``sys.modules`` by the finder."""

    def create_module(self, spec):  # type: ignore[override]
        return sys.modules.get(spec.name)

    def exec_module(self, module):  # type: ignore[override]
        # Module body was already executed when ``specstar.X`` was imported.
        return None


sys.meta_path.insert(0, _SpecstarRedirector())

# Top-level shim: emit the warning eagerly and re-export the public surface
# so ``from autocrud import <symbol>`` keeps working without forcing a
# submodule import path.
_warn_once(_PREFIX)
from specstar import *  # noqa: E402, F401, F403
