"""Fanout (sharding) layout for disk-backed stores — see #387.

These are pure local-filesystem unit tests (``tmp_path``) and must stay in
the fast CI lane, so the filename deliberately avoids the integration globs
in ``tests/conftest.py`` (``test_postgres_*`` etc.).
"""

from pathlib import Path

from specstar.resource_manager.blob_store.simple import (
    DiskBlobStore,
    _DiskBlobMeta,
)
from specstar.util.fanout import (
    SHARD_HEX_PER_LEVEL,
    SHARD_LEVELS,
    SHARD_ROOT,
    shard_segments,
    sharded_dir,
    sharded_path,
)


def _seed_legacy_blob(store, root, name, data, content_type="text/plain"):
    """Write a blob in the pre-#387 flat layout: raw file + sidecar at root."""
    (root / name).write_bytes(data)
    meta = _DiskBlobMeta(file_id=name, size=len(data), content_type=content_type)
    (root / f"{name}.blobmeta").write_bytes(store.encoder.encode(meta))


# ---------------------------------------------------------------------------
# helper
# ---------------------------------------------------------------------------


def test_shard_segments_shape_and_determinism():
    segs = shard_segments("hello-world")
    assert len(segs) == SHARD_LEVELS
    assert all(len(s) == SHARD_HEX_PER_LEVEL for s in segs)
    assert all(c in "0123456789abcdef" for s in segs for c in s)
    # deterministic
    assert shard_segments("hello-world") == segs


def test_shard_segments_spread():
    # Distinct names should not all collapse to one bucket.
    buckets = {shard_segments(f"name-{i}") for i in range(500)}
    assert len(buckets) > 100


def test_sharded_path_under_reserved_container(tmp_path: Path):
    p = sharded_path(tmp_path, "abc")
    assert p.parent.parent.parent.name == SHARD_ROOT
    assert p.name == "abc"
    assert p.relative_to(tmp_path).parts[0] == SHARD_ROOT


# ---------------------------------------------------------------------------
# blob store: write lands sharded, round-trips
# ---------------------------------------------------------------------------


def test_blob_put_lands_under_shard(tmp_path: Path):
    store = DiskBlobStore(tmp_path)
    b = store.put(b"payload", key="my-key")
    leaf = sharded_path(tmp_path, "my-key")
    assert leaf.exists(), "blob should be written into the sharded tree"
    # sidecar lives in the SAME shard directory
    assert (leaf.parent / "my-key.blobmeta").exists()
    # nothing left flat at the root (besides the _sh container / _sessions)
    flat = [
        c.name
        for c in tmp_path.iterdir()
        if c.is_file() and not c.name.endswith(".tmp")
    ]
    assert flat == []
    # round-trips
    assert store.get(b.file_id).data == b"payload"
    assert store.exists("my-key")


def test_blob_put_spreads_across_buckets(tmp_path: Path):
    store = DiskBlobStore(tmp_path)
    for i in range(300):
        store.put(f"data-{i}".encode(), key=f"key-{i}")
    shard_root = tmp_path / SHARD_ROOT
    level1 = [d for d in shard_root.iterdir() if d.is_dir()]
    assert len(level1) > 20, "objects should spread across many buckets"


def test_blob_get_stream_sharded(tmp_path: Path):
    store = DiskBlobStore(tmp_path)
    store.put(b"streamed-bytes", key="sk")
    info = store.get_stream("sk")
    assert b"".join(info.iterator) == b"streamed-bytes"


# ---------------------------------------------------------------------------
# blob store: legacy (pre-fanout, flat) read fallback
# ---------------------------------------------------------------------------


def test_blob_reads_legacy_flat_layout(tmp_path: Path):
    # Simulate a pre-#387 store: blob written flat at the root (+ sidecar).
    store = DiskBlobStore(tmp_path)
    _seed_legacy_blob(store, tmp_path, "legacy", b"old-data", "application/x-test")
    assert store.exists("legacy")
    got = store.get("legacy")
    assert got.data == b"old-data"
    assert got.content_type == "application/x-test"
    info = store.get_stream("legacy")
    assert b"".join(info.iterator) == b"old-data"
    assert info.content_type == "application/x-test"


# ---------------------------------------------------------------------------
# blob store: migration
# ---------------------------------------------------------------------------


def test_blob_migrate_layout_moves_legacy(tmp_path: Path):
    store = DiskBlobStore(tmp_path)
    # Seed legacy flat blobs (raw file + sidecar each).
    _seed_legacy_blob(store, tmp_path, "a", b"AAA")
    _seed_legacy_blob(store, tmp_path, "b", b"BBB")

    moved = store.migrate_layout()
    assert moved == 2  # sidecars move with their blob, not counted separately

    # Data + sidecars now live under the shard tree and still read back.
    assert sharded_path(tmp_path, "a").exists()
    assert sharded_path(tmp_path, "b").exists()
    assert (sharded_path(tmp_path, "a").parent / "a.blobmeta").exists()
    assert not (tmp_path / "a").exists()
    assert not (tmp_path / "a.blobmeta").exists()
    assert store.get("a").data == b"AAA"
    assert store.get("b").data == b"BBB"

    # Idempotent: a second run moves nothing.
    assert store.migrate_layout() == 0


def test_blob_migrate_layout_dry_run(tmp_path: Path):
    store = DiskBlobStore(tmp_path)
    (tmp_path / "x").write_bytes(b"XXX")
    would = store.migrate_layout(dry_run=True)
    assert would == 1
    # nothing actually moved
    assert (tmp_path / "x").exists()
    assert not sharded_path(tmp_path, "x").exists()


def test_blob_half_migrated_store_still_reads(tmp_path: Path):
    store = DiskBlobStore(tmp_path)
    # one sharded, one legacy
    store.put(b"new", key="fresh")
    _seed_legacy_blob(store, tmp_path, "stale", b"old")
    assert store.get("fresh").data == b"new"
    assert store.get("stale").data == b"old"


# ---------------------------------------------------------------------------
# meta store
# ---------------------------------------------------------------------------

from datetime import datetime  # noqa: E402

from specstar.query_types import ResourceMetaSearchQuery  # noqa: E402
from specstar.resource_manager.meta_store.simple import DiskMetaStore  # noqa: E402
from specstar.types import ResourceMeta  # noqa: E402

_T = datetime(2026, 1, 1)


def _meta(resource_id: str) -> ResourceMeta:
    return ResourceMeta(
        current_revision_id=f"{resource_id}:1",
        resource_id=resource_id,
        total_revision_count=1,
        created_time=_T,
        updated_time=_T,
        created_by="u",
        updated_by="u",
    )


def _disk_meta(tmp_path: Path) -> DiskMetaStore:
    return DiskMetaStore(encoding="msgpack", rootdir=tmp_path)  # ty:ignore[invalid-argument-type]


def test_meta_setitem_lands_under_shard(tmp_path: Path):
    store = _disk_meta(tmp_path)
    store["user:1"] = _meta("user:1")
    leaf = sharded_path(tmp_path, "user:1").with_name("user:1.data")
    assert leaf.exists()
    # nothing flat at the root
    assert [c.name for c in tmp_path.iterdir() if c.is_file()] == []
    # round-trips
    assert "user:1" in store
    assert store["user:1"].resource_id == "user:1"


def test_meta_iter_and_len_spread(tmp_path: Path):
    store = _disk_meta(tmp_path)
    for i in range(200):
        store[f"r:{i}"] = _meta(f"r:{i}")
    assert len(store) == 200
    assert set(store) == {f"r:{i}" for i in range(200)}
    shard_root = tmp_path / SHARD_ROOT
    assert len([d for d in shard_root.iterdir() if d.is_dir()]) > 15


def test_meta_reads_legacy_flat_layout(tmp_path: Path):
    store = _disk_meta(tmp_path)
    # Seed a pre-#387 flat record directly.
    legacy = tmp_path / "old:1.data"
    legacy.write_bytes(store._serializer.encode(_meta("old:1")))
    assert "old:1" in store
    assert store["old:1"].resource_id == "old:1"
    assert "old:1" in set(store)
    assert len(store) == 1


def test_meta_iter_search_across_layouts(tmp_path: Path):
    store = _disk_meta(tmp_path)
    (tmp_path / "leg:1.data").write_bytes(store._serializer.encode(_meta("leg:1")))
    store["new:1"] = _meta("new:1")
    found = {m.resource_id for m in store.iter_search(ResourceMetaSearchQuery())}
    assert found == {"leg:1", "new:1"}


def test_meta_migrate_layout(tmp_path: Path):
    store = _disk_meta(tmp_path)
    (tmp_path / "a:1.data").write_bytes(store._serializer.encode(_meta("a:1")))
    (tmp_path / "b:1.data").write_bytes(store._serializer.encode(_meta("b:1")))
    assert store.migrate_layout(dry_run=True) == 2
    assert (tmp_path / "a:1.data").exists()  # dry-run moved nothing

    assert store.migrate_layout() == 2
    assert sharded_path(tmp_path, "a:1").with_name("a:1.data").exists()
    assert not (tmp_path / "a:1.data").exists()
    assert store["a:1"].resource_id == "a:1"
    assert store.migrate_layout() == 0  # idempotent


def test_meta_setitem_clears_legacy_twin(tmp_path: Path):
    store = _disk_meta(tmp_path)
    (tmp_path / "k:1.data").write_bytes(store._serializer.encode(_meta("k:1")))
    store["k:1"] = _meta("k:1")  # write-through should drop the flat twin
    assert not (tmp_path / "k:1.data").exists()
    assert len(store) == 1
    del store["k:1"]
    assert "k:1" not in store


# ---------------------------------------------------------------------------
# resource store
# ---------------------------------------------------------------------------

import io  # noqa: E402
from uuid import uuid4  # noqa: E402

from specstar.resource_manager.resource_store.simple import (  # noqa: E402
    DiskResourceStore,
    relative_walk_up,
)
from specstar.types import RevisionInfo, RevisionStatus  # noqa: E402


def _rev_info(rid: str, rev: str, uid, sv="1.0") -> RevisionInfo:
    return RevisionInfo(
        uid=uid,
        resource_id=rid,
        revision_id=rev,
        schema_version=sv,
        status=RevisionStatus.stable,
        created_time=_T,
        updated_time=_T,
        created_by="u",
        updated_by="u",
        parent_revision_id=None,
        data_hash="h",
    )


def _disk_resource(tmp_path: Path) -> DiskResourceStore:
    return DiskResourceStore(encoding="msgpack", rootdir=tmp_path)  # ty:ignore[invalid-argument-type]


def _seed_legacy_revision(store, root, rid, rev, uid, data, sv="1.0"):
    """Recreate the pre-#387 flat resource layout by hand."""
    p_sv = "no_ver" if sv is None else f"v_{sv}"
    reald = root / "store" / str(uid)
    reald.mkdir(parents=True, exist_ok=True)
    (reald / "data").write_bytes(data)
    (reald / "info").write_bytes(
        store._info_serializer.encode(_rev_info(rid, rev, uid, sv))
    )
    symd = root / "resource" / rid / rev / p_sv
    symd.parent.mkdir(parents=True, exist_ok=True)
    symd.symlink_to(relative_walk_up(reald, symd.parent), target_is_directory=True)


def test_resource_save_lands_sharded_and_roundtrips(tmp_path: Path):
    store = _disk_resource(tmp_path)
    uid = uuid4()
    info = _rev_info("res:1", "res:1:1", uid)
    store.save(info, io.BytesIO(b'{"v":1}'))

    # symlink under sharded resource/, real data under sharded store/
    symd = sharded_dir(tmp_path / "resource", "res:1") / "res:1" / "res:1:1" / "v_1.0"
    assert symd.is_symlink()
    reald = sharded_dir(tmp_path / "store", str(uid)) / str(uid)
    assert (reald / "data").exists()
    # nothing flat
    assert [c.name for c in (tmp_path / "store").iterdir()] == [SHARD_ROOT]

    assert store.exists("res:1", "res:1:1", "1.0")
    with store.get_data_bytes("res:1", "res:1:1", "1.0") as f:
        assert f.read() == b'{"v":1}'
    assert store.get_revision_info("res:1", "res:1:1", "1.0").uid == uid


def test_resource_listings_sharded(tmp_path: Path):
    store = _disk_resource(tmp_path)
    for i in range(60):
        store.save(_rev_info(f"r:{i}", f"r:{i}:1", uuid4()), io.BytesIO(b"x"))
    assert set(store.list_resources()) == {f"r:{i}" for i in range(60)}
    assert list(store.list_revisions("r:3")) == ["r:3:1"]
    assert list(store.list_schema_versions("r:3", "r:3:1")) == ["1.0"]


def test_resource_reads_legacy_flat_layout(tmp_path: Path):
    store = _disk_resource(tmp_path)
    _seed_legacy_revision(store, tmp_path, "old:1", "old:1:1", uuid4(), b"LEGACY")
    assert store.exists("old:1", "old:1:1", "1.0")
    assert list(store.list_resources()) == ["old:1"]
    assert list(store.list_revisions("old:1")) == ["old:1:1"]
    with store.get_data_bytes("old:1", "old:1:1", "1.0") as f:
        assert f.read() == b"LEGACY"


def test_resource_migrate_layout(tmp_path: Path):
    store = _disk_resource(tmp_path)
    uid = uuid4()
    _seed_legacy_revision(store, tmp_path, "m:1", "m:1:1", uid, b"DATA")

    assert store.migrate_layout(dry_run=True) == 2  # 1 store dir + 1 symlink
    assert (tmp_path / "store" / str(uid)).exists()  # dry-run moved nothing

    assert store.migrate_layout() == 2
    # legacy trees drained
    assert not (tmp_path / "store" / str(uid)).exists()
    assert not (tmp_path / "resource" / "m:1").exists()
    # sharded data present and symlink resolves through to it
    reald = sharded_dir(tmp_path / "store", str(uid)) / str(uid)
    assert (reald / "data").read_bytes() == b"DATA"
    with store.get_data_bytes("m:1", "m:1:1", "1.0") as f:
        assert f.read() == b"DATA"
    assert store.migrate_layout() == 0  # idempotent


def test_resource_collect_orphans_across_layouts(tmp_path: Path):
    store = _disk_resource(tmp_path)
    live_uid = uuid4()
    store.save(_rev_info("live:1", "live:1:1", live_uid), io.BytesIO(b"L"))
    orphan_uid = uuid4()
    store.save(_rev_info("dead:1", "dead:1:1", orphan_uid), io.BytesIO(b"D"))

    removed = store.collect_orphans({"live:1"})
    assert removed >= 1
    assert store.exists("live:1", "live:1:1", "1.0")
    assert not store.exists("dead:1", "dead:1:1", "1.0")
    # the orphan's real data is reclaimed too
    assert not (
        sharded_dir(tmp_path / "store", str(orphan_uid)) / str(orphan_uid)
    ).exists()


def test_resource_purge_resource(tmp_path: Path):
    store = _disk_resource(tmp_path)
    uid = uuid4()
    store.save(_rev_info("p:1", "p:1:1", uid), io.BytesIO(b"P"))
    assert store.exists("p:1", "p:1:1", "1.0")
    store.purge_resource("p:1")
    assert not store.exists("p:1", "p:1:1", "1.0")
    assert not (sharded_dir(tmp_path / "store", str(uid)) / str(uid)).exists()
