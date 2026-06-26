"""End-to-end garbage-collection tests for blob ref-counting (issue #370).

Exercised at the ``SpecStar`` (crud) level with the default in-memory blob
store, driving the resource managers directly.

Timing note: a blob's *age* is its real wall-clock write time, while the GC's
``now`` is injected.  Tests therefore capture a reference time **before**
creating blobs and drive ``gc(now=...)`` relative to it — ``+2h`` clears the
default ``T1`` (1h) grace so orphans become quarantine-eligible, and ``+27h``
clears ``T1`` + ``T2`` (24h) so a quarantined orphan is deleted.
"""

import datetime as dt

import msgspec
from xxhash import xxh3_128_hexdigest

from specstar.crud.core import SpecStar
from specstar.types import Binary

UTC = dt.timezone.utc
T0 = dt.datetime(2026, 1, 1, tzinfo=UTC)  # revision timestamp (independent of blob age)


class Doc(msgspec.Struct):
    title: str
    file: Binary | None = None


class Note(msgspec.Struct):
    body: str
    attachment: Binary | None = None


def _create(spec: SpecStar, model_name: str, struct) -> str:
    rm = spec.resource_managers[model_name]
    with rm.using("alice", T0) as ops:
        info = ops.create(struct)
    return info.resource_id


def _perm_delete(spec: SpecStar, model_name: str, rid: str) -> None:
    rm = spec.resource_managers[model_name]
    with rm.using("alice", T0) as ops:
        ops.permanently_delete(rid)


def test_reconcile_collects_orphaned_blob():
    """A blob referenced only by a permanently-deleted resource is removed —
    but only after dwelling in quarantine past T2 (reversible until then)."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    fid = xxh3_128_hexdigest(b"orphan-payload")
    rid = _create(spec, "doc", Doc(title="t", file=Binary(data=b"orphan-payload")))
    assert spec.blob_store.exists(fid) is True

    _perm_delete(spec, "doc", rid)

    # First reconcile only quarantines (reversible) — blob still present.
    s1 = spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=2))
    assert s1.quarantined == 1
    assert s1.deleted == 0
    assert spec.blob_store.exists(fid) is True

    # After T2 the quarantined orphan is permanently removed.
    s2 = spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=27))
    assert s2.deleted == 1
    assert spec.blob_store.exists(fid) is False


def test_reconcile_keeps_blob_referenced_by_another_model():
    """The live set is the union across ALL models: a blob still referenced by
    a different model must survive even when one referencing resource is purged."""
    spec = SpecStar()
    spec.add_model(Doc)
    spec.add_model(Note)
    ref = dt.datetime.now(UTC)
    shared = b"shared-across-models"
    fid = xxh3_128_hexdigest(shared)

    doc_rid = _create(spec, "doc", Doc(title="d", file=Binary(data=shared)))
    _create(spec, "note", Note(body="n", attachment=Binary(data=shared)))

    _perm_delete(spec, "doc", doc_rid)

    spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=2))
    spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=27))

    # Note still references the shared blob → never collected.
    assert spec.blob_store.exists(fid) is True


def test_reconcile_keeps_blob_of_soft_deleted_resource():
    """Soft delete keeps the revision (and thus the blob) alive."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    fid = xxh3_128_hexdigest(b"soft-deleted-payload")
    rid = _create(
        spec, "doc", Doc(title="t", file=Binary(data=b"soft-deleted-payload"))
    )

    rm = spec.resource_managers["doc"]
    with rm.using("alice", T0) as ops:
        ops.delete(rid)  # soft delete — revision still stored

    spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=2))
    spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=27))

    assert spec.blob_store.exists(fid) is True


def test_reconcile_protects_fresh_unreferenced_blob_within_t1():
    """A freshly-written orphan is NOT quarantined while within the T1 grace —
    protecting the upload-then-reference window."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    fid = xxh3_128_hexdigest(b"fresh-orphan")
    rid = _create(spec, "doc", Doc(title="t", file=Binary(data=b"fresh-orphan")))

    _perm_delete(spec, "doc", rid)

    # now is only 30 min after creation — within the 1h T1 grace.
    stats = spec.gc(mode="reconcile", now=ref + dt.timedelta(minutes=30))
    assert stats.quarantined == 0
    assert spec.blob_store.exists(fid) is True


def test_reconcile_keeps_blob_referenced_again_before_delete():
    """A blob re-referenced while in quarantine is never deleted — the new
    reference resurrects it, so a later reconcile leaves it live."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    payload = b"comes-back-from-the-dead"
    fid = xxh3_128_hexdigest(payload)

    rid = _create(spec, "doc", Doc(title="a", file=Binary(data=payload)))
    _perm_delete(spec, "doc", rid)

    # Quarantine the now-orphaned blob.
    spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=2))

    # Before T2 elapses, a brand-new resource references the same content
    # (the write resurrects it out of quarantine immediately).
    _create(spec, "doc", Doc(title="b", file=Binary(data=payload)))

    # Even past T2, the blob is live again → never deleted.
    stats = spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=27))
    assert stats.deleted == 0
    assert spec.blob_store.exists(fid) is True


def test_incremental_quarantines_candidate_then_reconcile_deletes():
    """The cheap incremental pass quarantines blobs whose count hit zero on
    permanently_delete (no revision scan); reconcile later deletes them."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    fid = xxh3_128_hexdigest(b"incremental-orphan")
    rid = _create(spec, "doc", Doc(title="t", file=Binary(data=b"incremental-orphan")))

    _perm_delete(spec, "doc", rid)

    s_inc = spec.gc(mode="incremental", now=ref + dt.timedelta(hours=2))
    assert s_inc.quarantined == 1
    assert s_inc.deleted == 0  # incremental never deletes
    assert spec.blob_store.exists(fid) is True

    s_rec = spec.gc(mode="reconcile", now=ref + dt.timedelta(hours=27))
    assert s_rec.deleted == 1
    assert spec.blob_store.exists(fid) is False


def test_incremental_skips_blob_still_referenced_by_count():
    """incref/decref keep a still-shared blob's count > 0, so the incremental
    pass does not quarantine it."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    shared = b"shared-incremental"
    fid = xxh3_128_hexdigest(shared)

    r1 = _create(spec, "doc", Doc(title="1", file=Binary(data=shared)))  # count 1
    _create(spec, "doc", Doc(title="2", file=Binary(data=shared)))  # count 2
    _perm_delete(spec, "doc", r1)  # decref → count 1 (> 0)

    stats = spec.gc(mode="incremental", now=ref + dt.timedelta(hours=2))
    assert stats.quarantined == 0
    assert spec.blob_store.exists(fid) is True


def test_new_reference_resurrects_quarantined_blob_on_write():
    """Referencing a quarantined blob on a write resurrects it immediately
    (hot-path restore), without waiting for the next reconcile."""
    spec = SpecStar()
    spec.add_model(Doc)
    ref = dt.datetime.now(UTC)
    payload = b"resurrect-on-write"
    fid = xxh3_128_hexdigest(payload)

    rid = _create(spec, "doc", Doc(title="a", file=Binary(data=payload)))
    _perm_delete(spec, "doc", rid)
    spec.gc(mode="incremental", now=ref + dt.timedelta(hours=2))  # quarantined

    # A brand-new resource references the same content.
    _create(spec, "doc", Doc(title="b", file=Binary(data=payload)))

    quarantined = set(
        spec.blob_store.iter_quarantined(entered_before=ref + dt.timedelta(days=999))
    )
    assert fid not in quarantined
    assert fid in set(spec.blob_store.iter_active())
