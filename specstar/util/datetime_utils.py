"""Datetime normalisation helpers.

These utilities ensure consistent timezone-aware datetime handling
throughout SpecStar.  All public functions treat naive datetimes as
UTC and always return timezone-aware ``datetime`` objects.
"""

import datetime as dt

__all__ = ["ensure_aware"]


def ensure_aware(d: dt.datetime) -> dt.datetime:
    """Return *d* as a timezone-aware datetime.

    If *d* is already timezone-aware it is returned unchanged.
    If *d* is naive (``tzinfo is None``) it is assumed to be UTC and
    ``datetime.timezone.utc`` is attached via ``replace()``.

    Arguments:
        d: A ``datetime.datetime`` instance (naive or aware).

    Returns:
        A timezone-aware ``datetime.datetime`` in UTC.

    Examples:
        >>> import datetime as dt
        >>> ensure_aware(dt.datetime(2025, 1, 1))
        datetime.datetime(2025, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
        >>> aware = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
        >>> ensure_aware(aware) is aware
        True
    """
    if d.tzinfo is None:
        return d.replace(tzinfo=dt.timezone.utc)
    return d
