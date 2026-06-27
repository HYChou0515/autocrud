"""Per-model read/list access-scope predicate (issue #398, part A).

An ``access_scope`` is a per-model callable that maps the request user to a
row-level visibility predicate. specstar ANDs it into *every* read query
(list/search/count and every single-resource GET variant) at the
ResourceManager read layer, but only for request-originated reads — internal
``ResourceManager`` calls stay unscoped (see ``ResourceManager.using`` /
``apply_access_scope``).

The callable returns one of three things:

* a :class:`~specstar.query.ConditionBuilder` — restrict reads to rows matching
  the predicate (out-of-scope single GETs become ``404``; list/search/count are
  filtered at the storage layer);
* ``None`` — **deny all** (fail-closed): list/search/count return empty without
  hitting storage and single GETs return ``404``;
* :data:`UNRESTRICTED` — no restriction at all (admin / privileged users).

``None`` is fail-closed on purpose: a misconfigured predicate that accidentally
returns ``None`` hides everything rather than leaking it. "See everything" must
be requested explicitly by returning :data:`UNRESTRICTED`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final, Union

if TYPE_CHECKING:
    from specstar.query import ConditionBuilder


class _Unrestricted:
    """Singleton sentinel returned by an ``access_scope`` to skip scoping."""

    __slots__ = ()
    _instance: "_Unrestricted | None" = None

    def __new__(cls) -> "_Unrestricted":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "UNRESTRICTED"


UNRESTRICTED: Final[_Unrestricted] = _Unrestricted()
"""Return this from an ``access_scope`` to grant unrestricted read access."""


# A per-model read access-scope predicate: user -> visibility.
AccessScope = Callable[[str], Union["ConditionBuilder", None, _Unrestricted]]


__all__ = ["UNRESTRICTED", "AccessScope", "_Unrestricted"]
