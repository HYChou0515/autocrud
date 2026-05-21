"""Tests for ``specstar.defaults`` and ``specstar.id_generators``."""

from __future__ import annotations

import datetime as dt

from specstar import defaults, id_generators


def test_utcnow_returns_aware_utc_datetime() -> None:
    # Tracer: the builtin produces an aware datetime in UTC so
    # downstream comparisons aren't a naive/aware footgun.
    now = defaults.utcnow()
    assert isinstance(now, dt.datetime)
    assert now.tzinfo is not None
    assert now.utcoffset() == dt.timedelta(0)


def test_now_factory_returns_callable_in_named_tz() -> None:
    fn = defaults.now("Asia/Taipei")
    now = fn()
    assert now.tzinfo is not None
    # Taipei is UTC+8 (no DST), so offset is 8h.
    assert now.utcoffset() == dt.timedelta(hours=8)


def test_uuid4_returns_distinct_strings() -> None:
    a = id_generators.uuid4()
    b = id_generators.uuid4()
    assert isinstance(a, str)
    assert isinstance(b, str)
    assert a != b
    assert len(a) == 36  # canonical UUID hyphenated form
