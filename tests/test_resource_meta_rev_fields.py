"""Tests for ``ResourceMeta.rev_*`` (revision-level fields embedded in meta).

Covers:
- ``create`` / ``update`` / ``modify`` / ``switch`` populate ``rev_*``.
- ``ResourceMetaSearchQuery`` filters on the new fields.
- ``ResourceMetaSortKey.rev_created_time`` / ``rev_updated_time`` sort.
- ``backfill_revision_meta()`` patches legacy resources whose ``rev_*``
  fields are still ``UNSET``.
- Backwards-compat: msgspec decodes a meta written before the new
  fields existed (``rev_*`` are ``UNSET``).
"""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from msgspec import UNSET, Struct

from autocrud.crud.core import AutoCRUD
from autocrud.query import QB
from autocrud.query_types import (
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)
from autocrud.resource_manager.basic import is_match_query
from autocrud.resource_manager.core import ResourceManager
from autocrud.types import ResourceMeta, RevisionStatus


class User(Struct):
    name: str
    age: int


def _mgr_for_user() -> ResourceManager[User]:
    crud = AutoCRUD()
    crud.add_model(User)
    return crud.get_resource_manager(User)  # ty:ignore[invalid-return-type]


# ---------------------------------------------------------------------------
# create / update / modify / switch populate the rev_* fields
# ---------------------------------------------------------------------------


class TestRevFieldsPopulated:
    def test_create_populates_rev_fields(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1, 12, 0, 0)):
            info = mgr.create(User(name="Alice", age=30))
        meta = mgr.get_meta(info.resource_id)
        assert meta.rev_status == RevisionStatus.stable
        assert meta.rev_created_by == "alice"
        assert meta.rev_updated_by == "alice"
        assert meta.rev_created_time == info.created_time
        assert meta.rev_updated_time == info.updated_time

    def test_create_draft_populates_status(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info = mgr.create(User(name="A", age=1), status=RevisionStatus.draft)
        meta = mgr.get_meta(info.resource_id)
        assert meta.rev_status == RevisionStatus.draft
        assert info.status == RevisionStatus.draft

    def test_update_refreshes_rev_fields(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info = mgr.create(User(name="A", age=1))
        with mgr.using("bob", dt.datetime(2026, 2, 2)):
            new_info = mgr.update(info.resource_id, User(name="B", age=2))
        meta = mgr.get_meta(info.resource_id)
        # rev_created_by reflects the *new* current revision's creator (bob)
        assert meta.rev_created_by == "bob"
        assert meta.rev_updated_by == "bob"
        assert meta.rev_created_time == new_info.created_time
        # original resource creator is unchanged on the resource-level field
        assert meta.created_by == "alice"

    def test_modify_refreshes_rev_updated_time(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info = mgr.create(User(name="A", age=1), status=RevisionStatus.draft)
        with mgr.using("alice", dt.datetime(2026, 1, 2)):
            new_info = mgr.modify(info.resource_id, User(name="A2", age=2))
        meta = mgr.get_meta(info.resource_id)
        # modify keeps the same revision id, so created_time stays the same
        assert meta.rev_created_time == info.created_time
        assert meta.rev_updated_time == new_info.updated_time

    def test_switch_back_refreshes_rev_fields(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info_a = mgr.create(User(name="A", age=1))
        with mgr.using("bob", dt.datetime(2026, 2, 2)):
            mgr.update(info_a.resource_id, User(name="B", age=2))

        # After update: rev_created_by == bob (the new current revision)
        meta_after_update = mgr.get_meta(info_a.resource_id)
        assert meta_after_update.rev_created_by == "bob"

        # Switch back to revision 1 — rev_* should now mirror that revision
        with mgr.using("carol", dt.datetime(2026, 3, 3)):
            mgr.switch(info_a.resource_id, info_a.revision_id)
        meta = mgr.get_meta(info_a.resource_id)
        assert meta.current_revision_id == info_a.revision_id
        assert meta.rev_created_by == "alice"
        assert meta.rev_updated_by == "alice"
        assert meta.rev_created_time == info_a.created_time


# ---------------------------------------------------------------------------
# ResourceMetaSearchQuery filters
# ---------------------------------------------------------------------------


class TestRevSearchQueryFilters:
    @staticmethod
    def _make_meta(**overrides) -> ResourceMeta:
        meta = ResourceMeta(
            current_revision_id="r:1",
            resource_id="r",
            total_revision_count=1,
            created_time=dt.datetime(2026, 1, 1),
            updated_time=dt.datetime(2026, 1, 1),
            created_by="alice",
            updated_by="alice",
        )
        for key, value in overrides.items():
            setattr(meta, key, value)
        return meta

    def test_rev_status_filter(self):
        meta_draft = self._make_meta(rev_status=RevisionStatus.draft)
        meta_stable = self._make_meta(rev_status=RevisionStatus.stable)
        meta_legacy = self._make_meta()  # rev_status UNSET

        q = ResourceMetaSearchQuery(rev_statuses=["draft"])
        assert is_match_query(meta_draft, q)
        assert not is_match_query(meta_stable, q)
        assert not is_match_query(meta_legacy, q)

    def test_rev_created_by_filter(self):
        m_alice = self._make_meta(rev_created_by="alice")
        m_bob = self._make_meta(rev_created_by="bob")
        m_legacy = self._make_meta()
        q = ResourceMetaSearchQuery(rev_created_bys=["alice"])
        assert is_match_query(m_alice, q)
        assert not is_match_query(m_bob, q)
        assert not is_match_query(m_legacy, q)

    def test_rev_time_range_filter(self):
        m_old = self._make_meta(rev_created_time=dt.datetime(2026, 1, 1))
        m_new = self._make_meta(rev_created_time=dt.datetime(2026, 6, 1))
        m_legacy = self._make_meta()
        q = ResourceMetaSearchQuery(
            rev_created_time_start=dt.datetime(2026, 3, 1),
        )
        assert not is_match_query(m_old, q)
        assert is_match_query(m_new, q)
        assert not is_match_query(m_legacy, q)


# ---------------------------------------------------------------------------
# Search via ResourceManager (memory store) — end-to-end
# ---------------------------------------------------------------------------


class TestSearchEndToEnd:
    def test_search_by_rev_created_by(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info_a = mgr.create(User(name="A", age=1))
            info_b = mgr.create(User(name="B", age=2))
        with mgr.using("bob", dt.datetime(2026, 2, 2)):
            mgr.update(info_b.resource_id, User(name="B2", age=22))

        # rev_created_by == "alice": only info_a (info_b's current rev is now bob's)
        q = ResourceMetaSearchQuery(rev_created_bys=["alice"])
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [info_a.resource_id]

        q2 = ResourceMetaSearchQuery(rev_created_bys=["bob"])
        ids2 = sorted(m.resource_id for m in mgr.search_resources(q2))
        assert ids2 == [info_b.resource_id]

    def test_search_by_rev_status(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info_draft = mgr.create(User(name="d", age=1), status=RevisionStatus.draft)
            info_stable = mgr.create(
                User(name="s", age=2), status=RevisionStatus.stable
            )

        q = ResourceMetaSearchQuery(rev_statuses=[RevisionStatus.draft.value])
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [info_draft.resource_id]
        # sanity: stable filter returns the other one
        q_stable = ResourceMetaSearchQuery(rev_statuses=[RevisionStatus.stable.value])
        ids_stable = sorted(m.resource_id for m in mgr.search_resources(q_stable))
        assert ids_stable == [info_stable.resource_id]

    def test_sort_by_rev_created_time(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 3, 1)):
            info_late = mgr.create(User(name="late", age=1))
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info_early = mgr.create(User(name="early", age=2))

        q = ResourceMetaSearchQuery(
            sorts=[
                ResourceMetaSearchSort(
                    key=ResourceMetaSortKey.rev_created_time,
                    direction=ResourceMetaSortDirection.ascending,
                )
            ]
        )
        ids = [m.resource_id for m in mgr.search_resources(q)]
        assert ids == [info_early.resource_id, info_late.resource_id]


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------


class TestBackfill:
    def test_backfill_populates_legacy_meta(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            info = mgr.create(User(name="A", age=1))

        # Simulate an upgrade: a meta written before rev_* existed has them all UNSET.
        meta = mgr.get_meta(info.resource_id)
        meta.rev_status = UNSET
        meta.rev_created_by = UNSET
        meta.rev_updated_by = UNSET
        meta.rev_created_time = UNSET
        meta.rev_updated_time = UNSET
        mgr.storage.save_meta(meta)

        # Confirm they're truly cleared
        before = mgr.get_meta(info.resource_id)
        assert before.rev_status is UNSET

        n = mgr.backfill_revision_meta()
        assert n == 1

        after = mgr.get_meta(info.resource_id)
        assert after.rev_status == RevisionStatus.stable
        assert after.rev_created_by == "alice"
        assert after.rev_created_time == info.created_time

    def test_backfill_skips_already_filled(self):
        mgr = _mgr_for_user()
        with mgr.using("alice", dt.datetime(2026, 1, 1)):
            mgr.create(User(name="A", age=1))
        # First call: nothing to backfill — every create() already populates.
        assert mgr.backfill_revision_meta() == 0


# ---------------------------------------------------------------------------
# Backwards compatibility (msgspec default value)
# ---------------------------------------------------------------------------


class TestBackwardsCompatibility:
    def test_decode_meta_without_rev_fields(self):
        """A blob serialized before ``rev_*`` existed must still decode."""
        from typing import cast

        from autocrud.resource_manager.basic import MsgspecSerializer

        ser = MsgspecSerializer(
            encoding="json",  # ty:ignore[invalid-argument-type]
            resource_type=ResourceMeta,
        )
        legacy_blob = (
            b'{"current_revision_id":"r:1","resource_id":"r","schema_version":null,'
            b'"total_revision_count":1,'
            b'"created_time":"2026-01-01T00:00:00",'
            b'"updated_time":"2026-01-01T00:00:00",'
            b'"created_by":"alice","updated_by":"alice","is_deleted":false}'
        )
        meta = cast(ResourceMeta, ser.decode(legacy_blob))
        assert meta.resource_id == "r"
        assert meta.rev_status is UNSET
        assert meta.rev_created_by is UNSET
        assert meta.rev_created_time is UNSET


# ---------------------------------------------------------------------------
# QB conditions on rev_* fields — Python API
# ---------------------------------------------------------------------------


def _seed_three_resources(
    mgr: ResourceManager[User],
) -> tuple[str, str, str]:
    """Three resources with distinct rev_* footprints, returns (id_alice_draft,
    id_alice_stable, id_bob_stable_after_update)."""
    with mgr.using("alice", dt.datetime(2026, 1, 1)):
        info_a = mgr.create(User(name="A", age=10), status=RevisionStatus.draft)
    with mgr.using("alice", dt.datetime(2026, 2, 1)):
        info_b = mgr.create(User(name="B", age=20))
    with mgr.using("alice", dt.datetime(2026, 3, 1)):
        info_c = mgr.create(User(name="C", age=30))
    # Update C — its current revision now belongs to bob
    with mgr.using("bob", dt.datetime(2026, 6, 1)):
        mgr.update(info_c.resource_id, User(name="C2", age=33))
    return info_a.resource_id, info_b.resource_id, info_c.resource_id


class TestQBPythonOnRevFields:
    """Build queries via the QB DSL directly (no HTTP)."""

    def test_qb_eq_on_rev_status(self) -> None:
        mgr: ResourceManager[User] = _mgr_for_user()
        id_draft, _id_stable_alice, _id_stable_bob = _seed_three_resources(mgr)

        q = QB.rev_status().eq(RevisionStatus.draft.value).build()
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [id_draft]

    def test_qb_in_list_on_rev_created_by(self) -> None:
        mgr: ResourceManager[User] = _mgr_for_user()
        _id_draft, _id_stable_alice, id_stable_bob = _seed_three_resources(mgr)

        q = QB.rev_created_by().in_(["bob"]).build()
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [id_stable_bob]

    def test_qb_ne_on_rev_updated_by(self) -> None:
        mgr: ResourceManager[User] = _mgr_for_user()
        id_draft, id_stable_alice, _id_stable_bob = _seed_three_resources(mgr)

        q = QB.rev_updated_by().ne("bob").build()
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == sorted([id_draft, id_stable_alice])

    def test_qb_gte_on_rev_created_time(self) -> None:
        mgr: ResourceManager[User] = _mgr_for_user()
        _id_draft, _id_stable_alice, id_stable_bob = _seed_three_resources(mgr)

        # Cut-off at 2026-02-15 — should include B (Feb 1? no, before) and C-after-update.
        # Actually: A=Jan, B=Feb, C-current-rev=Jun. So >= Feb 15 returns just C.
        q = QB.rev_created_time().gte(dt.datetime(2026, 2, 15)).build()
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [id_stable_bob]

    def test_qb_compound_and_or_on_rev_fields(self) -> None:
        """Compose `(rev_created_by == alice) & (rev_status == stable)`."""
        mgr: ResourceManager[User] = _mgr_for_user()
        _id_draft, id_stable_alice, _id_stable_bob = _seed_three_resources(mgr)

        q = (
            (QB.rev_created_by().eq("alice"))
            & (QB.rev_status().eq(RevisionStatus.stable.value))
        ).build()
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [id_stable_alice]

    def test_qb_combine_rev_field_with_data_field(self) -> None:
        """rev_* condition AND a regular indexed-data condition."""
        crud = AutoCRUD()
        crud.add_model(User, indexed_fields=[("age", int)])
        mgr: ResourceManager[User] = crud.get_resource_manager(User)  # ty:ignore[invalid-assignment]
        _id_draft, id_stable_alice, _id_stable_bob = _seed_three_resources(mgr)

        # All resources where rev_created_by == alice AND age > 15
        # → A (age 10) excluded by age, C (age 33 but bob) excluded by user,
        # → B (age 20, alice) is the only match.
        q = ((QB.rev_created_by().eq("alice")) & (QB["age"] > 15)).build()
        ids = sorted(m.resource_id for m in mgr.search_resources(q))
        assert ids == [id_stable_alice]


# ---------------------------------------------------------------------------
# QB conditions on rev_* fields — HTTP layer
# ---------------------------------------------------------------------------


_ClientAndIds = tuple[TestClient, tuple[str, str, str]]


class TestQBHttpOnRevFields:
    """Send the QB expression as a `?qb=...` query string, exercise the route."""

    @pytest.fixture
    def client_and_ids(self) -> _ClientAndIds:
        app = FastAPI()
        router = APIRouter()
        crud = AutoCRUD()
        crud.add_model(User, indexed_fields=[("age", int), ("name", str)])
        crud.apply(router)
        app.include_router(router)
        client = TestClient(app)

        mgr: ResourceManager[User] = crud.get_resource_manager(User)  # ty:ignore[invalid-assignment]
        id_draft, id_stable_alice, id_stable_bob = _seed_three_resources(mgr)
        return client, (id_draft, id_stable_alice, id_stable_bob)

    def test_http_qb_filter_by_rev_status(self, client_and_ids: _ClientAndIds) -> None:
        client, (_id_draft, _, _) = client_and_ids
        resp = client.get(
            "/user/data",
            params={"qb": "QB.rev_status() == 'draft'"},
        )
        assert resp.status_code == 200, resp.text
        # `/user/data` returns just data, but we can verify count
        assert len(resp.json()) == 1

    def test_http_qb_filter_by_rev_created_by(
        self, client_and_ids: _ClientAndIds
    ) -> None:
        client, (_, id_stable_alice, id_stable_bob) = client_and_ids

        resp_alice = client.get(
            "/user", params={"qb": "QB.rev_created_by() == 'alice'", "returns": "meta"}
        )
        assert resp_alice.status_code == 200, resp_alice.text
        # alice owns A (draft) and B (stable). C's current rev is bob's now.
        ids = sorted(item["meta"]["resource_id"] for item in resp_alice.json())
        assert id_stable_alice in ids
        assert id_stable_bob not in ids

        resp_bob = client.get(
            "/user", params={"qb": "QB.rev_created_by() == 'bob'", "returns": "meta"}
        )
        assert resp_bob.status_code == 200, resp_bob.text
        bob_ids = [item["meta"]["resource_id"] for item in resp_bob.json()]
        assert bob_ids == [id_stable_bob]

    def test_http_qb_compound_and(self, client_and_ids: _ClientAndIds) -> None:
        client, (_, id_stable_alice, _) = client_and_ids
        resp = client.get(
            "/user",
            params={
                "qb": "(QB.rev_created_by() == 'alice') & (QB.rev_status() == 'stable')",
                "returns": "meta",
            },
        )
        assert resp.status_code == 200, resp.text
        ids = [item["meta"]["resource_id"] for item in resp.json()]
        assert ids == [id_stable_alice]

    def test_http_qb_in_list_rev_updated_by(
        self, client_and_ids: _ClientAndIds
    ) -> None:
        client, (_, _, id_stable_bob) = client_and_ids
        resp = client.get(
            "/user",
            params={
                "qb": "QB.rev_updated_by().in_(['bob'])",
                "returns": "meta",
            },
        )
        assert resp.status_code == 200, resp.text
        ids = [item["meta"]["resource_id"] for item in resp.json()]
        assert ids == [id_stable_bob]

    def test_http_qb_lt_on_rev_created_time(
        self, client_and_ids: _ClientAndIds
    ) -> None:
        client, (id_draft, id_stable_alice, _) = client_and_ids
        # Resources whose current revision was created before 2026-02-15.
        # → A (Jan) and B (Feb 1) both qualify; C's current rev is Jun.
        # The qb parser resolves bare ``datetime`` to the *module*, so we
        # need ``datetime.datetime(...)`` to construct an instance.
        cutoff = "datetime.datetime(2026, 2, 15)"
        resp = client.get(
            "/user",
            params={
                "qb": f"QB.rev_created_time() < {cutoff}",
                "returns": "meta",
            },
        )
        assert resp.status_code == 200, resp.text
        ids = sorted(item["meta"]["resource_id"] for item in resp.json())
        assert ids == sorted([id_draft, id_stable_alice])

    def test_http_qb_combine_rev_with_data_field(
        self, client_and_ids: _ClientAndIds
    ) -> None:
        client, (_, id_stable_alice, _) = client_and_ids
        resp = client.get(
            "/user",
            params={
                "qb": "(QB.rev_created_by() == 'alice') & (QB['age'] > 15)",
                "returns": "meta",
            },
        )
        assert resp.status_code == 200, resp.text
        ids = [item["meta"]["resource_id"] for item in resp.json()]
        assert ids == [id_stable_alice]

    def test_http_qb_conflict_with_rev_query_param(
        self, client_and_ids: _ClientAndIds
    ) -> None:
        """`?qb=...` may not be combined with the `rev_*` URL params."""
        client, _ = client_and_ids
        resp = client.get(
            "/user",
            params={
                "qb": "QB.rev_status() == 'stable'",
                "rev_statuses": ["draft"],
            },
        )
        # 422 from the conflict guard in build_query()
        assert resp.status_code == 422, resp.text
        assert "rev_statuses" in resp.text

    def test_http_rev_query_params_without_qb(
        self, client_and_ids: _ClientAndIds
    ) -> None:
        """The new `?rev_statuses=...` URL params work standalone too."""
        client, (id_draft, _, _) = client_and_ids
        resp = client.get(
            "/user",
            params={"rev_statuses": ["draft"], "returns": "meta"},
        )
        assert resp.status_code == 200, resp.text
        ids = [item["meta"]["resource_id"] for item in resp.json()]
        assert ids == [id_draft]


@pytest.mark.parametrize(
    "field_name,sort_key",
    [
        ("rev_created_time", ResourceMetaSortKey.rev_created_time),
        ("rev_updated_time", ResourceMetaSortKey.rev_updated_time),
    ],
)
def test_resource_meta_sort_key_includes_rev_fields(field_name, sort_key):
    """Smoke test that the new sort keys resolve to their string values."""
    assert sort_key.value == field_name
