"""Tests for revision pruning — issue #377.

Covers the ResourceManager-level :meth:`prune_revisions` selection semantics
and the store-level :meth:`delete_revisions` primitive (memory + disk).
Postgres lives in ``test_postgres_prune_revisions.py`` (integration).
"""

import datetime as dt
import io
from uuid import uuid4

import msgspec
import pytest
from msgspec import Struct
from xxhash import xxh3_128_hexdigest

from specstar.crud.core import SpecStar
from specstar.events import IEventHandler
from specstar.resource_manager.basic import Encoding, IResourceStore
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import DiskMetaStore, MemoryMetaStore
from specstar.resource_manager.resource_store.simple import (
    DiskResourceStore,
    MemoryResourceStore,
)
from specstar.types import Binary, ResourceIDNotFoundError, RevisionInfo, RevisionStatus

UTC = dt.timezone.utc


class Item(Struct):
    name: str
    value: int = 0


def t(minute: int) -> dt.datetime:
    return dt.datetime(2025, 1, 1, tzinfo=UTC) + dt.timedelta(minutes=minute)


def _suffixes(revs) -> list[int]:
    """The trailing ``:N`` sequence numbers of a set of revision ids."""
    return sorted(int(r.rsplit(":", 1)[-1]) for r in revs)


# ── Parametrised over the two pruning-capable simple backends ──────────


@pytest.fixture(params=["memory", "disk"])
def storage(request, tmp_path):
    if request.param == "memory":
        return SimpleStorage(MemoryMetaStore(), MemoryResourceStore())
    return SimpleStorage(
        DiskMetaStore(rootdir=tmp_path / "meta"),
        DiskResourceStore(rootdir=tmp_path / "data"),
    )


def make_rm(storage, **kwargs) -> ResourceManager:
    return ResourceManager(Item, storage=storage, **kwargs)


def seed(rm, n: int = 5) -> str:
    """Create a resource with revisions v1..vn at times t(1)..t(n)."""
    with rm.using(user="a") as op:
        info = op.create(Item(name="v1"), now=t(1))
        rid = info.resource_id
        for i in range(2, n + 1):
            op.update(rid, Item(name=f"v{i}"), now=t(i))
    return rid


# ── prune_revisions: keep_last_n ──────────────────────────────────────


class TestKeepLastN:
    def test_keeps_newest_n(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 5)
        pruned = rm.prune_revisions(rid, keep_last_n=2, user="a", now=t(50))
        assert _suffixes(pruned) == [1, 2, 3]
        assert _suffixes(rm.list_revisions(rid)) == [4, 5]

    def test_preserves_current_and_count_is_monotonic(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 5)
        before = rm.get_meta(rid)
        rm.prune_revisions(rid, keep_last_n=2, user="a", now=t(50))
        after = rm.get_meta(rid)
        assert after.current_revision_id == before.current_revision_id
        # total_revision_count seeds new revision ids — must never shrink.
        assert after.total_revision_count == before.total_revision_count == 5
        # current revision still fully readable after the prune.
        assert rm.get(rid).data.name == "v5"

    def test_next_write_does_not_collide_after_prune(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 5)
        rm.prune_revisions(rid, keep_last_n=1, user="a", now=t(50))
        with rm.using(user="a") as op:
            info = op.update(rid, Item(name="v6"), now=t(51))
        # Sequence keeps climbing from total_revision_count, not the live count.
        assert info.revision_id == f"{rid}:6"
        assert rm.get(rid).data.name == "v6"

    def test_pruned_revision_data_is_gone(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 5)
        pruned = rm.prune_revisions(rid, keep_last_n=2, user="a", now=t(50))
        for r in pruned:
            assert rm.revision_exists(rid, r) is False
        for r in rm.list_revisions(rid):
            assert rm.revision_exists(rid, r) is True

    def test_floor_is_one_current_always_survives(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 3)
        pruned = rm.prune_revisions(rid, keep_last_n=1, user="a", now=t(50))
        assert _suffixes(pruned) == [1, 2]
        assert _suffixes(rm.list_revisions(rid)) == [3]


# ── prune_revisions: before (age) ─────────────────────────────────────


class TestBefore:
    def test_prunes_strictly_older(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 5)
        pruned = rm.prune_revisions(rid, before=t(3), user="a", now=t(50))
        # created at t(1), t(2) are < t(3); t(3..5) are kept.
        assert _suffixes(pruned) == [1, 2]
        assert _suffixes(rm.list_revisions(rid)) == [3, 4, 5]

    def test_never_prunes_current_even_when_old(self, storage):
        """Switch current back to an old revision, then age-prune everything
        before 'now': the current revision is retained regardless."""
        rm = make_rm(storage)
        rid = seed(rm, 5)
        rm.switch(rid, f"{rid}:2", user="a", now=t(20))
        pruned = rm.prune_revisions(rid, before=t(50), user="a", now=t(60))
        remaining = rm.list_revisions(rid)
        assert f"{rid}:2" in remaining  # current survived the age cutoff
        assert f"{rid}:2" not in pruned
        assert rm.get(rid).data.name == "v2"


# ── prune_revisions: union of both knobs ──────────────────────────────


class TestUnion:
    def test_union_is_conservative(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 5)
        # keep top-2 {4,5} ∪ {created>=t(3)} {3,4,5} = {3,4,5}.
        # Pruned only when beyond N AND older than before → {1,2}.
        pruned = rm.prune_revisions(
            rid, keep_last_n=2, before=t(3), user="a", now=t(50)
        )
        assert _suffixes(pruned) == [1, 2]
        assert _suffixes(rm.list_revisions(rid)) == [3, 4, 5]


# ── prune_revisions: lineage / 直系 ranking ───────────────────────────


class TestLineage:
    def test_lineal_ancestors_outrank_collateral_branches(self, storage):
        """After switching current to v3, the lineage is {1,2,3} and {4,5} are
        collateral. keep_last_n=2 keeps the current's recent ancestry, not the
        chronologically newer collateral branch."""
        rm = make_rm(storage)
        rid = seed(rm, 5)
        rm.switch(rid, f"{rid}:3", user="a", now=t(20))
        pruned = rm.prune_revisions(rid, keep_last_n=2, user="a", now=t(50))
        # ordered by (lineal, time): [3,2,1] then [5,4]; top-2 = {3,2}.
        assert _suffixes(pruned) == [1, 4, 5]
        assert _suffixes(rm.list_revisions(rid)) == [2, 3]
        assert rm.get(rid).data.name == "v3"

    def test_same_timestamp_orders_by_sequence(self, storage):
        """Revisions written at one ``now`` still order by authoring sequence,
        so keep_last_n is deterministic on batch-created history."""
        rm = make_rm(storage)
        with rm.using(user="a", now=t(7)) as op:  # every revision shares t(7)
            info = op.create(Item(name="v1"))
            rid = info.resource_id
            for i in range(2, 5):
                op.update(rid, Item(name=f"v{i}"))
        pruned = rm.prune_revisions(rid, keep_last_n=1, user="a", now=t(50))
        assert _suffixes(pruned) == [1, 2, 3]
        assert _suffixes(rm.list_revisions(rid)) == [4]


# ── prune_revisions: validation, no-op, errors, soft-delete ───────────


class TestEdges:
    def test_requires_a_knob(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 2)
        with pytest.raises(ValueError):
            rm.prune_revisions(rid, user="a", now=t(50))

    def test_keep_last_n_must_be_positive(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 2)
        with pytest.raises(ValueError):
            rm.prune_revisions(rid, keep_last_n=0, user="a", now=t(50))

    def test_noop_when_nothing_matches(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 3)
        assert rm.prune_revisions(rid, keep_last_n=10, user="a", now=t(50)) == []
        assert _suffixes(rm.list_revisions(rid)) == [1, 2, 3]

    def test_single_revision_is_noop(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 1)
        assert rm.prune_revisions(rid, keep_last_n=1, user="a", now=t(50)) == []

    def test_missing_resource_raises(self, storage):
        rm = make_rm(storage)
        with pytest.raises(ResourceIDNotFoundError):
            rm.prune_revisions("nope", keep_last_n=1, user="a", now=t(50))

    def test_soft_deleted_resource_is_prunable(self, storage):
        rm = make_rm(storage)
        rid = seed(rm, 4)
        rm.delete(rid, user="a", now=t(10))
        assert rm.get_meta(rid, include_deleted=True).is_deleted is True
        pruned = rm.prune_revisions(rid, keep_last_n=1, user="a", now=t(50))
        assert _suffixes(pruned) == [1, 2, 3]
        assert _suffixes(rm.list_revisions(rid)) == [4]


# ── prune_revisions: events ───────────────────────────────────────────


class _Spy(IEventHandler):
    def __init__(self):
        self.seen = []

    def is_supported(self, ctx) -> bool:
        return type(ctx).__name__.endswith("Prune")

    def handle_event(self, ctx) -> None:
        self.seen.append((type(ctx).__name__, getattr(ctx, "pruned", None)))


class TestEvents:
    def test_lifecycle_events_fire_with_pruned_payload(self, storage):
        spy = _Spy()
        rm = make_rm(storage, event_handlers=[spy])
        rid = seed(rm, 4)
        pruned = rm.prune_revisions(rid, keep_last_n=1, user="a", now=t(50))
        names = [n for n, _ in spy.seen]
        assert "BeforePrune" in names
        assert "OnSuccessPrune" in names
        assert "AfterPrune" in names
        success_payload = next(p for n, p in spy.seen if n == "OnSuccessPrune")
        assert sorted(success_payload) == sorted(pruned)


# ── store-level delete_revisions primitive ────────────────────────────


def _info(resource_id, revision_id, uid, *, schema_version=None, created=None):
    now = created or dt.datetime.now(UTC)
    return RevisionInfo(
        uid=uid,
        resource_id=resource_id,
        revision_id=revision_id,
        schema_version=schema_version,
        status=RevisionStatus.stable,
        created_time=now,
        updated_time=now,
        created_by="u",
        updated_by="u",
        parent_revision_id=None,
        data_hash="h",
    )


@pytest.fixture(params=["memory", "disk"])
def resource_store(request, tmp_path) -> IResourceStore:
    if request.param == "memory":
        return MemoryResourceStore(encoding=Encoding.json)
    return DiskResourceStore(encoding=Encoding.json, rootdir=tmp_path)


class TestDeleteRevisionsPrimitive:
    def test_removes_listed_revisions_only(self, resource_store):
        rid = "res"
        for n in range(1, 4):
            resource_store.save(
                _info(rid, f"{rid}:{n}", uuid4()), io.BytesIO(f"d{n}".encode())
            )
        resource_store.delete_revisions(rid, [f"{rid}:1", f"{rid}:2"])
        assert sorted(resource_store.list_revisions(rid)) == [f"{rid}:3"]

    def test_idempotent_on_unknown_revisions(self, resource_store):
        rid = "res"
        resource_store.save(_info(rid, f"{rid}:1", uuid4()), io.BytesIO(b"d"))
        # Deleting a non-existent revision (or twice) must not raise.
        resource_store.delete_revisions(rid, [f"{rid}:9"])
        resource_store.delete_revisions(rid, [f"{rid}:1"])
        resource_store.delete_revisions(rid, [f"{rid}:1"])
        assert list(resource_store.list_revisions(rid)) == []

    def test_shared_uid_payload_is_refcounted(self, resource_store):
        """Two revisions backed by the same uid: deleting one must keep the
        shared payload alive until the last referrer is gone."""
        rid = "res"
        shared = uuid4()
        resource_store.save(_info(rid, f"{rid}:1", shared), io.BytesIO(b"shared"))
        resource_store.save(_info(rid, f"{rid}:2", shared), io.BytesIO(b"shared"))
        resource_store.save(_info(rid, f"{rid}:3", uuid4()), io.BytesIO(b"solo"))

        resource_store.delete_revisions(rid, [f"{rid}:1"])
        # rev2 still references the shared uid → its data is intact.
        with resource_store.get_data_bytes(rid, f"{rid}:2", None) as fh:
            assert fh.read() == b"shared"

        resource_store.delete_revisions(rid, [f"{rid}:2"])
        # Last referrer gone → shared payload reclaimed; solo rev untouched.
        with resource_store.get_data_bytes(rid, f"{rid}:3", None) as fh:
            assert fh.read() == b"solo"


# ── blob decref integration (#370) ────────────────────────────────────


class Doc(msgspec.Struct):
    title: str
    file: Binary | None = None


class TestBlobDecref:
    def test_prune_decrefs_only_pruned_revisions_blobs(self):
        spec = SpecStar()
        spec.add_model(Doc)
        rm = spec.resource_managers["doc"]
        ref = dt.datetime.now(UTC)
        seed_time = dt.datetime(2026, 1, 1, tzinfo=UTC)

        fid_a = xxh3_128_hexdigest(b"payload-A")
        fid_b = xxh3_128_hexdigest(b"payload-B")
        with rm.using("alice", seed_time) as op:
            info = op.create(Doc(title="a", file=Binary(data=b"payload-A")))
            rid = info.resource_id
            op.update(rid, Doc(title="b", file=Binary(data=b"payload-B")))

        assert spec.blob_store.exists(fid_a)
        pruned = rm.prune_revisions(rid, keep_last_n=1, user="alice", now=seed_time)
        assert _suffixes(pruned) == [1]

        # The pruned revision's blob is now orphaned and gets collected; the
        # current revision's blob is retained (still referenced).
        spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=2))
        spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=27))
        assert spec.blob_store.exists(fid_a) is False
        assert spec.blob_store.exists(fid_b) is True
        assert rm.get(rid).data.title == "b"


# ── S3 explicitly defers to a follow-up (#377 scope) ──────────────────


def test_s3_does_not_implement_delete_revisions():
    s3 = pytest.importorskip("specstar.resource_manager.resource_store.s3")
    # S3 inherits the base NotImplementedError stub (parity with its missing
    # purge_resource); revision pruning on S3 is deliberately out of scope.
    assert s3.S3ResourceStore.delete_revisions is IResourceStore.delete_revisions
