"""Bounded-retry helpers for transient filesystem errors.

Issue #352: on NFS, a concurrent rename/unlink on another client invalidates
the inode the kernel handed us. The next syscall raises
``OSError(errno=ESTALE)`` — a *transient* signal that the right answer is
"re-stat and try again", not "crash the request".

Local filesystems normally surface the same race as ``FileNotFoundError``
(ENOENT), which the disk stores already handle as "the key is genuinely
gone". ESTALE is different: the file usually still exists, just under a
new inode after an atomic rename. A short bounded retry resolves it
without the caller noticing.

The helpers here intentionally only treat ESTALE as transient — ENOENT
and other ``OSError`` subclasses keep their existing semantics so we don't
mask real "missing file" / "permission denied" bugs.
"""

from __future__ import annotations

import errno
import random
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

_TRANSIENT_ERRNOS = frozenset({errno.ESTALE})

# Tunable defaults — small enough that we don't add measurable latency to
# the happy path (the loop runs once on success), big enough that a real
# NFS rename storm has time to settle.
DEFAULT_ATTEMPTS = 5
DEFAULT_BASE_DELAY = 0.005  # 5 ms
DEFAULT_MAX_DELAY = 0.2  # 200 ms cap on a single backoff


def is_transient_fs_error(exc: BaseException) -> bool:
    """True if *exc* is an OSError whose errno is treated as retry-worthy.

    Currently only ``errno.ESTALE`` qualifies. ENOENT is *not* transient —
    callers that need "skip missing files" already handle it explicitly.
    """
    return isinstance(exc, OSError) and exc.errno in _TRANSIENT_ERRNOS


def retry_on_estale(
    fn: Callable[..., T],
    *args,
    attempts: int = DEFAULT_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    **kwargs,
) -> T:
    """Run *fn(*args, **kwargs)* with bounded retries on ESTALE.

    Backoff grows exponentially from *base_delay* (clamped to *max_delay*)
    and is jittered by a uniform [0.5, 1.5) multiplier so concurrent
    workers don't all retry in lock-step.

    Non-ESTALE exceptions propagate immediately. After *attempts* tries the
    last ESTALE is re-raised so callers can still log / surface a clear
    "filesystem is genuinely broken" signal.
    """
    last: OSError | None = None
    for attempt in range(attempts):
        try:
            return fn(*args, **kwargs)
        except OSError as exc:
            if not is_transient_fs_error(exc):
                raise
            last = exc
            if attempt == attempts - 1:
                break
            delay = min(max_delay, base_delay * (2**attempt))
            time.sleep(delay * (0.5 + random.random()))
    assert last is not None
    raise last
