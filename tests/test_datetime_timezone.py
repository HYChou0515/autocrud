"""Tests for offset-naive vs offset-aware datetime consistency.

Bug: revision-list endpoint with ``sort=-created_time`` raises
``TypeError: can't compare offset-naive and offset-aware datetimes``
when some RevisionInfo objects carry naive ``created_time`` and others
carry UTC-aware ``created_time`` (e.g. after a msgpack round-trip).

Root cause locations:
- ``DependencyProvider._create_default_now_dependency`` returns naive
  ``dt.datetime.now()``.
- ``get_sort_fn`` in basic.py compares ``meta.created_time`` values
  that may have mixed timezone awareness.
- Revision-list sort in get.py ``revision_infos.sort(...)`` hits the
  same mixed-comparison issue.
- ``created_time_start``/``created_time_end`` filters compare an
  ISO-parsed datetime (possibly aware) against stored datetimes
  (possibly naive).
"""

import datetime as dt
import uuid

import msgspec
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from autocrud.crud.core import AutoCRUD
from autocrud.crud.route_templates.basic import DependencyProvider
from autocrud.crud.route_templates.create import CreateRouteTemplate
from autocrud.crud.route_templates.get import ReadRouteTemplate
from autocrud.crud.route_templates.update import UpdateRouteTemplate
from autocrud.resource_manager.basic import (
    Encoding,
    MsgspecSerializer,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    get_sort_fn,
)
from autocrud.types import (
    ResourceMeta,
    ResourceMetaSearchSort,
    RevisionInfo,
    RevisionStatus,
)
from autocrud.util.datetime_utils import ensure_aware

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Item(msgspec.Struct):
    name: str
    value: int = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_revision_info(
    resource_id: str = "r1",
    revision_id: str = "r1:1",
    created_time: dt.datetime | None = None,
    status: RevisionStatus = RevisionStatus.stable,
) -> RevisionInfo:
    """Build a minimal RevisionInfo for testing."""
    now = created_time or dt.datetime.now()
    return RevisionInfo(
        resource_id=resource_id,
        revision_id=revision_id,
        uid=uuid.uuid4(),
        parent_revision_id=None,
        schema_version=None,
        status=status,
        created_time=now,
        updated_time=now,
        created_by="test",
        updated_by="test",
    )


def _make_resource_meta(
    resource_id: str = "r1",
    created_time: dt.datetime | None = None,
    updated_time: dt.datetime | None = None,
) -> ResourceMeta:
    """Build a minimal ResourceMeta for testing."""
    now = created_time or dt.datetime.now()
    return ResourceMeta(
        resource_id=resource_id,
        current_revision_id=f"{resource_id}:1",
        total_revision_count=1,
        created_time=now,
        updated_time=updated_time or now,
        created_by="test",
        updated_by="test",
    )


# ===================================================================
# 1. default_get_now should return timezone-aware datetime
# ===================================================================


class TestDefaultGetNowTimezone:
    """DependencyProvider.default_get_now 應回傳 UTC-aware datetime."""

    def test_default_get_now_is_timezone_aware(self):
        """default_get_now() 回傳的 datetime 必須帶有 tzinfo."""
        deps = DependencyProvider()
        get_now = deps.get_now
        # Simulate calling the dependency (FastAPI-style)
        result = get_now()
        assert result.tzinfo is not None, (
            "default_get_now() returned a naive datetime; expected UTC-aware"
        )

    def test_default_get_now_is_utc(self):
        """default_get_now() 回傳的 datetime 應該是 UTC."""
        deps = DependencyProvider()
        result = deps.get_now()
        assert result.tzinfo == dt.timezone.utc or (
            result.utcoffset() == dt.timedelta(0)
        ), "default_get_now() should return UTC datetime"


# ===================================================================
# 2. Revision-list sort must handle mixed naive/aware datetimes
# ===================================================================


class TestRevisionListMixedDatetimeSort:
    """Sorting RevisionInfo objects with mixed naive/aware created_time
    must not raise TypeError."""

    def test_sort_mixed_naive_and_aware_revision_infos(self):
        """透過 ensure_aware 排序混合 naive/aware 的 RevisionInfo 列表不應報錯.

        這模擬了 get.py 中
        ``revision_infos.sort(key=lambda r: ensure_aware(r.created_time), reverse=True)``
        的場景。
        """
        naive_time = dt.datetime(2025, 1, 1, 12, 0, 0)
        aware_time = dt.datetime(2025, 1, 1, 13, 0, 0, tzinfo=dt.timezone.utc)

        rev_naive = _make_revision_info(revision_id="r1:1", created_time=naive_time)
        rev_aware = _make_revision_info(revision_id="r1:2", created_time=aware_time)

        infos = [rev_naive, rev_aware]
        # This should NOT raise TypeError
        infos.sort(key=lambda r: ensure_aware(r.created_time), reverse=True)
        assert len(infos) == 2
        assert infos[0].revision_id == "r1:2"  # 13:00 UTC > 12:00 UTC

    def test_sort_mixed_naive_and_aware_ascending(self):
        """升序排序混合 naive/aware 的 RevisionInfo 不應報錯."""
        naive_time = dt.datetime(2025, 6, 15, 10, 0, 0)
        aware_time = dt.datetime(2025, 6, 15, 9, 0, 0, tzinfo=dt.timezone.utc)

        rev_naive = _make_revision_info(revision_id="r1:1", created_time=naive_time)
        rev_aware = _make_revision_info(revision_id="r1:2", created_time=aware_time)

        infos = [rev_aware, rev_naive]
        infos.sort(key=lambda r: ensure_aware(r.created_time))
        assert infos[0].revision_id == "r1:2"  # 09:00 UTC < 10:00 UTC


# ===================================================================
# 3. get_sort_fn must handle mixed naive/aware meta datetimes
# ===================================================================


class TestGetSortFnMixedDatetime:
    """get_sort_fn (basic.py) 在比較 ResourceMeta 時
    若 created_time 混合 naive/aware 不應拋出 TypeError."""

    def test_get_sort_fn_created_time_mixed_awareness(self):
        """對 created_time 排序，一個 naive 一個 aware，不應報錯."""
        naive_time = dt.datetime(2025, 3, 1, 8, 0, 0)
        aware_time = dt.datetime(2025, 3, 1, 9, 0, 0, tzinfo=dt.timezone.utc)

        meta_naive = _make_resource_meta(resource_id="a", created_time=naive_time)
        meta_aware = _make_resource_meta(resource_id="b", created_time=aware_time)

        sort_key = get_sort_fn(
            [
                ResourceMetaSearchSort(
                    key=ResourceMetaSortKey.created_time,
                    direction=ResourceMetaSortDirection.ascending,
                )
            ]
        )

        metas = [meta_aware, meta_naive]
        # Should NOT raise TypeError
        metas.sort(key=sort_key)
        assert len(metas) == 2

    def test_get_sort_fn_updated_time_mixed_awareness(self):
        """對 updated_time 排序，一個 naive 一個 aware，不應報錯."""
        naive_time = dt.datetime(2025, 5, 10, 12, 0, 0)
        aware_time = dt.datetime(2025, 5, 10, 13, 0, 0, tzinfo=dt.timezone.utc)

        meta_naive = _make_resource_meta(
            resource_id="a",
            created_time=dt.datetime(2025, 1, 1),
            updated_time=naive_time,
        )
        meta_aware = _make_resource_meta(
            resource_id="b",
            created_time=dt.datetime(2025, 1, 1),
            updated_time=aware_time,
        )

        sort_key = get_sort_fn(
            [
                ResourceMetaSearchSort(
                    key=ResourceMetaSortKey.updated_time,
                    direction=ResourceMetaSortDirection.descending,
                )
            ]
        )

        metas = [meta_naive, meta_aware]
        metas.sort(key=sort_key)
        assert len(metas) == 2


# ===================================================================
# 4. created_time_start/end filter must handle mixed awareness
# ===================================================================


class TestCreatedTimeFilterMixedDatetime:
    """Revision-list 的 created_time_start/end 過濾在比較 aware ISO
    字串解析結果與 naive/aware revision created_time 時不應報錯."""

    def test_filter_aware_start_against_naive_revision(self):
        """UTC-aware 的 start filter 比較 naive revision.created_time.

        使用 ensure_aware 後兩者可安全比較。"""
        naive_time = dt.datetime(2025, 3, 1, 10, 0, 0)
        start_dt = ensure_aware(dt.datetime.fromisoformat("2025-03-01T09:00:00+00:00"))

        rev = _make_revision_info(created_time=naive_time)
        # Simulates the filter in get.py L463 — now using ensure_aware
        result = ensure_aware(rev.created_time) >= start_dt
        assert result is True  # 10:00 UTC >= 09:00 UTC

    def test_filter_naive_start_against_aware_revision(self):
        """Naive 的 start filter 比較 aware revision.created_time."""
        aware_time = dt.datetime(2025, 3, 1, 10, 0, 0, tzinfo=dt.timezone.utc)
        start_dt = ensure_aware(dt.datetime.fromisoformat("2025-03-01T09:00:00"))

        rev = _make_revision_info(created_time=aware_time)
        result = ensure_aware(rev.created_time) >= start_dt
        assert result is True  # 10:00 UTC >= 09:00 UTC

    def test_filter_aware_end_against_naive_revision(self):
        """UTC-aware 的 end filter 比較 naive revision.created_time."""
        naive_time = dt.datetime(2025, 3, 1, 10, 0, 0)
        end_dt = ensure_aware(dt.datetime.fromisoformat("2025-03-01T11:00:00+00:00"))

        rev = _make_revision_info(created_time=naive_time)
        result = ensure_aware(rev.created_time) <= end_dt
        assert result is True  # 10:00 UTC <= 11:00 UTC


# ===================================================================
# 5. msgpack round-trip changes naive → aware (documenting the issue)
# ===================================================================


class TestMsgpackDatetimeRoundTrip:
    """msgpack serialization of RevisionInfo converts naive datetime
    to UTC-aware — this documents the root cause of the bug."""

    def test_naive_datetime_becomes_aware_after_msgpack_roundtrip(self):
        """Naive datetime 經過 msgpack encode/decode 後應該還是 naive,
        或者整個系統統一使用 aware datetime 避免不一致。"""
        naive_time = dt.datetime(2025, 6, 1, 12, 0, 0)
        info = _make_revision_info(created_time=naive_time)

        serializer = MsgspecSerializer(
            encoding=Encoding.msgpack, resource_type=RevisionInfo
        )
        encoded = serializer.encode(info)
        decoded = serializer.decode(encoded)

        # After msgpack round-trip, the datetime should remain
        # consistent with the input (both naive or both aware).
        # Currently msgpack makes it aware — if the fix normalizes to
        # always-aware, this test documents the expected behaviour.
        assert decoded.created_time.tzinfo is None or (
            info.created_time.tzinfo is not None
        ), (
            "msgpack round-trip changed naive datetime to aware; "
            "this inconsistency causes TypeError on comparison. "
            f"Input tzinfo={info.created_time.tzinfo}, "
            f"Output tzinfo={decoded.created_time.tzinfo}"
        )

    def test_aware_datetime_stays_aware_after_msgpack_roundtrip(self):
        """Aware datetime 還是 aware 不變."""
        aware_time = dt.datetime(2025, 6, 1, 12, 0, 0, tzinfo=dt.timezone.utc)
        info = _make_revision_info(created_time=aware_time)

        serializer = MsgspecSerializer(
            encoding=Encoding.msgpack, resource_type=RevisionInfo
        )
        encoded = serializer.encode(info)
        decoded = serializer.decode(encoded)

        assert decoded.created_time.tzinfo is not None
        assert decoded.created_time == aware_time


# ===================================================================
# 6. Integration: revision-list API with mixed datetime awareness
# ===================================================================


class TestRevisionListAPITimezone:
    """End-to-end: revision-list endpoint should work correctly
    even when revisions have mixed naive/aware created_time."""

    @pytest.fixture
    def mixed_tz_client(self):
        """Build a FastAPI TestClient where two revisions have
        different timezone awareness on their created_time.

        We achieve this by toggling the ``get_now`` dependency between
        calls — first returning naive, then returning aware datetime.
        """
        call_count = 0

        def alternating_now() -> dt.datetime:
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 1:
                # Odd calls: naive datetime
                return dt.datetime(2025, 3, 1, 10, 0, 0)
            else:
                # Even calls: UTC-aware datetime
                return dt.datetime(2025, 3, 1, 11, 0, 0, tzinfo=dt.timezone.utc)

        deps = DependencyProvider(get_now=alternating_now)
        crud = AutoCRUD(model_naming="kebab")
        crud.add_route_template(CreateRouteTemplate(dependency_provider=deps))
        crud.add_route_template(ReadRouteTemplate(dependency_provider=deps))
        crud.add_route_template(UpdateRouteTemplate(dependency_provider=deps))
        crud.add_model(Item)

        app = FastAPI()
        router = APIRouter()
        crud.apply(router)
        app.include_router(router)
        return TestClient(app)

    def test_revision_list_sort_descending_mixed_tz(self, mixed_tz_client):
        """revision-list?sort=-created_time 在混合 tz 下不應 500."""
        client = mixed_tz_client

        # Create: uses call 1 (naive) for create + call 2 (aware) for meta
        resp = client.post("/item", json={"name": "v1", "value": 1})
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]

        # Update: uses next calls — generates another revision
        resp = client.put(f"/item/{rid}", json={"name": "v2", "value": 2})
        assert resp.status_code == 200

        # Revision list with sort — should NOT return 500
        resp = client.get(
            f"/item/{rid}/revision-list?sort=-created_time&chain_only=false"
        )
        assert resp.status_code == 200, (
            f"revision-list returned {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert len(data["revisions"]) >= 2

    def test_revision_list_sort_ascending_mixed_tz(self, mixed_tz_client):
        """revision-list?sort=created_time 在混合 tz 下不應 500."""
        client = mixed_tz_client

        resp = client.post("/item", json={"name": "a1", "value": 10})
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]

        resp = client.put(f"/item/{rid}", json={"name": "a2", "value": 20})
        assert resp.status_code == 200

        resp = client.get(
            f"/item/{rid}/revision-list?sort=created_time&chain_only=false"
        )
        assert resp.status_code == 200, (
            f"revision-list returned {resp.status_code}: {resp.text}"
        )

    def test_revision_list_time_filter_mixed_tz(self, mixed_tz_client):
        """revision-list 的 created_time_start filter 在混合 tz 下不應 500."""
        client = mixed_tz_client

        resp = client.post("/item", json={"name": "f1", "value": 100})
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]

        resp = client.put(f"/item/{rid}", json={"name": "f2", "value": 200})
        assert resp.status_code == 200

        # Filter with an aware timestamp
        resp = client.get(
            f"/item/{rid}/revision-list"
            f"?created_time_start=2025-03-01T00:00:00%2B00:00"
            f"&chain_only=false"
        )
        assert resp.status_code == 200, (
            f"revision-list with time filter returned {resp.status_code}: {resp.text}"
        )
