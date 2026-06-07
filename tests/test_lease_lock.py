"""#342 #2 — lease-based distributed lock primitive.

``spec.lock(key, ttl)`` / ``try_lock`` / ``renew_lock`` / ``release_lock`` give
write workflows the cross-worker mutex they need when CAS isn't enough — e.g.
a multi-step pipeline that must serialize per collection without holding a
DB transaction the whole way through.

The TTL (lease) means a crashed holder can't deadlock the key forever: once
the lease expires, anyone can re-acquire.

Single-process default is in-memory. A pluggable ``ILockBackend`` lets a
multi-worker deployment swap in Redis / Postgres advisory locks — one line
in ``spec.configure()``.
"""

import time

import pytest

from specstar import SpecStar
from specstar.locks import (
    LockHandle,
    LockHeldError,
    LockNotOwnedError,
)


def _spec() -> SpecStar:
    sp = SpecStar()
    sp.configure(default_user="t")
    return sp


def test_try_lock_on_free_key_returns_handle():
    sp = _spec()
    handle = sp.try_lock("k1", ttl=60)
    assert isinstance(handle, LockHandle)
    assert handle.key == "k1"
    assert handle.token  # opaque ownership nonce


def test_try_lock_on_held_key_returns_none():
    sp = _spec()
    sp.try_lock("k1", ttl=60)
    assert sp.try_lock("k1", ttl=60) is None  # already held


def test_release_lock_frees_the_key():
    sp = _spec()
    h = sp.try_lock("k1", ttl=60)
    sp.release_lock(h)
    assert sp.try_lock("k1", ttl=60) is not None  # available again


def test_release_lock_with_wrong_token_raises():
    # Holder A's release must not free B's lock — token is the ownership proof.
    sp = _spec()
    real = sp.try_lock("k1", ttl=60)
    fake = LockHandle(key="k1", token="wrong", expires_at=real.expires_at)
    with pytest.raises(LockNotOwnedError):
        sp.release_lock(fake)


def test_expired_lock_can_be_reacquired_by_a_new_caller():
    # The TTL is the anti-deadlock guarantee — a crashed holder must not
    # block forever.
    sp = _spec()
    sp.try_lock("k1", ttl=0.05)
    time.sleep(0.1)
    assert sp.try_lock("k1", ttl=60) is not None


def test_renew_lock_extends_ttl():
    sp = _spec()
    h = sp.try_lock("k1", ttl=0.05)
    sp.renew_lock(h, ttl=60)
    time.sleep(0.1)  # past the ORIGINAL ttl
    assert sp.try_lock("k1", ttl=60) is None  # still held after renew


def test_renew_lock_with_wrong_token_raises():
    sp = _spec()
    sp.try_lock("k1", ttl=60)
    bogus = LockHandle(key="k1", token="not-yours", expires_at=time.monotonic() + 60)
    with pytest.raises(LockNotOwnedError):
        sp.renew_lock(bogus, ttl=60)


def test_lock_context_manager_acquires_and_releases():
    sp = _spec()
    with sp.lock("k1", ttl=60):
        # inside: another caller is locked out
        assert sp.try_lock("k1", ttl=60) is None
    # outside: lock released
    assert sp.try_lock("k1", ttl=60) is not None


def test_lock_context_manager_raises_when_held():
    sp = _spec()
    sp.try_lock("k1", ttl=60)
    with pytest.raises(LockHeldError):
        with sp.lock("k1", ttl=60):
            pass  # pragma: no cover


def test_different_keys_are_independent():
    sp = _spec()
    a = sp.try_lock("a", ttl=60)
    b = sp.try_lock("b", ttl=60)
    assert a is not None and b is not None
