"""Lease-based distributed lock primitive (#342 follow-up #2).

A lock here is *advisory* and *leased*: callers cooperate by checking the lock
before doing work, and every grant carries a TTL so a crashed holder cannot
deadlock the key forever. After the lease expires, the next caller can
re-acquire — the new owner gets a fresh token, and any operation using the
old token is rejected.

The default backend is in-memory (single-process). A multi-worker deployment
swaps in a Redis / Postgres / etcd backend through ``spec.configure(
lock_backend=...)``; the backend protocol is intentionally small.

Token discipline:
    Every grant returns a ``LockHandle`` with an opaque ``token`` — a nonce
    rotated on each acquisition. ``release_lock`` and ``renew_lock`` require
    the holder's token; a wrong token raises :class:`LockNotOwnedError`. This
    prevents a stale handle (e.g. from a previous lease window) from
    releasing the *new* owner's lock.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Protocol

import msgspec


class LockHandle(msgspec.Struct, frozen=True, kw_only=True):
    """Opaque ownership token returned by :meth:`SpecStar.try_lock`.

    Hold this and pass it back to :meth:`SpecStar.release_lock` /
    :meth:`SpecStar.renew_lock` to prove you are the current owner. The
    ``token`` field is the proof-of-ownership nonce — never derive it
    yourself; only the backend issues valid tokens.
    """

    key: str
    token: str
    expires_at: float  # monotonic-clock deadline


class LockHeldError(RuntimeError):
    """Raised by :meth:`SpecStar.lock` (the context-manager form) when the
    key is already held by someone else.

    The non-blocking :meth:`try_lock` returns ``None`` in this case; the
    context manager raises so a ``with`` block can't silently proceed when
    the lock wasn't acquired.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"lock {key!r} is already held")
        self.key = key


class LockNotOwnedError(RuntimeError):
    """Raised by :meth:`release_lock` / :meth:`renew_lock` when the supplied
    handle's token does not match the current owner's token.

    This protects against two stale-handle scenarios: a release after the
    lease expired and a new owner took over, and a buggy caller using a
    handle returned to a different worker.
    """

    def __init__(self, key: str) -> None:
        super().__init__(f"handle for lock {key!r} is not the current owner")
        self.key = key


class ILockBackend(Protocol):
    """Minimal contract for a lease-lock storage backend.

    A backend owns the atomic compare-and-set semantics. Implementations:
    in-memory (default), Redis ``SET NX PX`` + Lua release, Postgres
    advisory locks with a TTL row, etcd lease, etc.
    """

    def try_acquire(self, key: str, ttl: float) -> LockHandle | None:
        """Atomically acquire ``key`` if free (or its lease has expired).

        Returns a fresh ``LockHandle`` on success, ``None`` if held.
        """

    def release(self, handle: LockHandle) -> None:
        """Release ``key`` iff the handle's token still matches the owner.

        Raises :class:`LockNotOwnedError` on mismatch (stale handle / not
        the current owner). A no-op if the lease already expired *and*
        nobody re-acquired — releasing a phantom is fine.
        """

    def renew(self, handle: LockHandle, ttl: float) -> LockHandle:
        """Extend the lease iff the handle's token still matches.

        Returns a new ``LockHandle`` with an updated ``expires_at``. Raises
        :class:`LockNotOwnedError` if a different owner took over (e.g.
        the prior lease expired before ``renew`` arrived).
        """


class InMemoryLockBackend:
    """Single-process, threadsafe lease-lock backend.

    Suitable for tests, single-worker deployments, and the default-out-of-
    the-box experience. For multi-worker deployments, swap in a Redis or
    Postgres backend via ``spec.configure(lock_backend=...)``.
    """

    def __init__(self) -> None:
        self._mu = threading.Lock()
        # key -> (token, expires_at_monotonic)
        self._held: dict[str, tuple[str, float]] = {}

    def _expired(self, expires_at: float) -> bool:
        return time.monotonic() >= expires_at

    def try_acquire(self, key: str, ttl: float) -> LockHandle | None:
        with self._mu:
            current = self._held.get(key)
            if current is not None and not self._expired(current[1]):
                return None
            token = secrets.token_urlsafe(16)
            expires_at = time.monotonic() + ttl
            self._held[key] = (token, expires_at)
            return LockHandle(key=key, token=token, expires_at=expires_at)

    def release(self, handle: LockHandle) -> None:
        with self._mu:
            current = self._held.get(handle.key)
            if current is None:
                # Already gone — releasing a phantom (expired + reaped) is
                # benign. The "wrong-token" check below is what catches
                # actual ownership violations.
                return
            token, _expires_at = current
            if token != handle.token:
                raise LockNotOwnedError(handle.key)
            del self._held[handle.key]

    def renew(self, handle: LockHandle, ttl: float) -> LockHandle:
        with self._mu:
            current = self._held.get(handle.key)
            if current is None or current[0] != handle.token:
                raise LockNotOwnedError(handle.key)
            expires_at = time.monotonic() + ttl
            self._held[handle.key] = (handle.token, expires_at)
            return LockHandle(key=handle.key, token=handle.token, expires_at=expires_at)


__all__ = [
    "ILockBackend",
    "InMemoryLockBackend",
    "LockHandle",
    "LockHeldError",
    "LockNotOwnedError",
]
