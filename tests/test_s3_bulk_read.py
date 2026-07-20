"""S3 bulk read under a memory budget (issue #434).

Needs a live S3 / MinIO at ``SPECSTAR_TEST_S3_ENDPOINT`` (defaults to the
repo's local MinIO); auto-marked ``integration`` by ``tests/conftest.py``.

Reaching a payload on S3 takes two calls — GET the uid index, then GET the
object — so ``S3ResourceStore`` overrides ``read_many`` wholesale and fans
every stage out over a thread pool. ``head_object`` gives the size without
the body, which is what lets the budget be packed exactly; the generic
fallback would overshoot by one row. The packing tests below therefore
double as proof the override is the code path being taken.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import uuid

import pytest

try:
    import boto3  # noqa: F401

    from specstar.resource_manager.resource_store.s3 import S3ResourceStore
except ImportError:  # pragma: no cover
    pytest.skip("boto3 not installed", allow_module_level=True)

from specstar.types import RevisionInfo, RevisionStatus

S3_ENDPOINT = os.environ.get("SPECSTAR_TEST_S3_ENDPOINT", "http://localhost:9000")

_NOW = dt.datetime(2026, 7, 20, tzinfo=dt.timezone.utc)


def _s3_reachable() -> bool:
    try:
        S3ResourceStore(endpoint_url=S3_ENDPOINT, bucket="specstar-434-probe")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _s3_reachable(), reason="no live S3/MinIO at SPECSTAR_TEST_S3_ENDPOINT"
)


@pytest.fixture
def store():
    return S3ResourceStore(
        endpoint_url=S3_ENDPOINT,
        bucket="specstar-434-test",
        prefix=f"{uuid.uuid4().hex[:12]}/",
    )


def _info(resource_id: str) -> RevisionInfo:
    return RevisionInfo(
        uid=uuid.uuid4(),
        resource_id=resource_id,
        revision_id="r1",
        schema_version=None,
        status=RevisionStatus.stable,
        created_time=_NOW,
        updated_time=_NOW,
        created_by="tester",
        updated_by="tester",
    )


def _seed(store, sizes: dict[str, int]) -> list[tuple[str, str, None]]:
    keys: list[tuple[str, str, None]] = []
    for rid, size in sizes.items():
        info = _info(rid)
        store.save(info, io.BytesIO(b"x" * size))
        keys.append((rid, info.revision_id, info.schema_version))
    return keys


def test_read_many_packs_the_budget_exactly(store):
    """40 bytes fits a(10)+b(20); c(30) overflows and is left for next round.

    The generic fallback would have consumed all three — it only notices the
    overflow after fetching c. Exact packing means ``head_object`` sized the
    batch before any body was transferred.
    """
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=40)

    assert consumed == 2
    assert data == {"a": b"x" * 10, "b": b"x" * 20}


def test_read_many_returns_the_whole_batch_when_the_budget_is_ample(store):
    keys = _seed(store, {"a": 10, "b": 20, "c": 30})

    data, consumed = store.read_many(keys, max_bytes=10_000)

    assert consumed == 3
    assert data == {"a": b"x" * 10, "b": b"x" * 20, "c": b"x" * 30}


def test_read_many_always_makes_progress(store):
    keys = _seed(store, {"huge": 5_000})

    data, consumed = store.read_many(keys, max_bytes=1)

    assert consumed == 1
    assert data == {"huge": b"x" * 5_000}


def test_read_many_omits_rows_that_are_not_there(store):
    keys = _seed(store, {"a": 10, "c": 30})
    keys.insert(1, ("ghost", "r1", None))  # never saved

    data, consumed = store.read_many(keys, max_bytes=10_000)

    assert consumed == 3
    assert set(data) == {"a", "c"}


def test_read_many_preserves_order_when_draining_batch_by_batch(store):
    """Draining a prefix at a time must eventually cover every row."""
    keys = _seed(store, {"a": 30, "b": 30, "c": 30})

    seen: dict[str, bytes] = {}
    pending = list(keys)
    while pending:
        data, consumed = store.read_many(pending, max_bytes=40)
        assert consumed == 1  # 40 bytes fits exactly one 30-byte row
        seen.update(data)
        pending = pending[consumed:]

    assert seen.keys() == {"a", "b", "c"}


def test_read_many_with_no_items_makes_no_calls(store):
    assert store.read_many([], max_bytes=1_000) == ({}, 0)
