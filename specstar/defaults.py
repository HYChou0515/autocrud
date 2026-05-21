"""Built-in callables for ``default_now`` and similar declarative slots.

``default_now`` on ``add_model`` (or ``spec.configure``) accepts any
``Callable[[], datetime]``. Without these built-ins, every spec-driven
project would have to write a tiny lambda — or worse, ``string_ref``
to a user module that just wraps ``datetime.now``. These two helpers
cover the 95% case (UTC and named timezones) so the LLM can emit a
deterministic, importable reference instead.
"""

from __future__ import annotations

import datetime as _dt
from collections.abc import Callable
from zoneinfo import ZoneInfo


def utcnow() -> _dt.datetime:
    """Return an aware UTC datetime — the boring, safe default."""
    return _dt.datetime.now(_dt.timezone.utc)


def now(tz: str) -> Callable[[], _dt.datetime]:
    """Factory: return a callable that produces aware ``tz``-local datetimes.

    Example::

        # spec.md ### Defaults
        # - default_now: Asia/Taipei
        spec.add_model(..., default_now=specstar.defaults.now("Asia/Taipei"))
    """
    zone = ZoneInfo(tz)

    def _now() -> _dt.datetime:
        return _dt.datetime.now(zone)

    _now.__name__ = f"now({tz!r})"
    return _now
