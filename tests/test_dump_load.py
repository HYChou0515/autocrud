"""Tests for the new streaming-msgpack dump/load system.

Covers:
- DumpStreamWriter / DumpStreamReader roundtrip
- BinaryProcessor.collect_file_ids
- ResourceManager dump with QB filter
- ResourceManager load with OnDuplicate strategies
- AutoCRUD dump with model_queries
- AutoCRUD load (incremental)
- Full roundtrip with blobs
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from msgspec import Struct

from autocrud.crud.core import AutoCRUD, LoadStats
from autocrud.query import QB
from autocrud.resource_manager.binary_processor import BinaryProcessor
from autocrud.resource_manager.dump_format import (
    BlobRecord,
    DumpStreamReader,
    DumpStreamWriter,
    EofRecord,
    HeaderRecord,
    MetaRecord,
    ModelEndRecord,
    ModelStartRecord,
    RevisionRecord,
)
from autocrud.types import Binary, DuplicateResourceError, OnDuplicate

# ---------------------------------------------------------------------------
# Test models
# ---------------------------------------------------------------------------


class Item(Struct):
    name: str
    value: int


class Widget(Struct):
    label: str
    weight: float = 0.0


class BlobItem(Struct):
    name: str
    attachment: Binary | None = None


class NestedBlobItem(Struct):
    name: str
    files: list[Binary] = []
    metadata: dict[str, Binary] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud(*models, indexed_fields=None, **kw) -> AutoCRUD:
    crud = AutoCRUD(**kw)
    for m in models:
        crud.add_model(m, indexed_fields=indexed_fields)
    return crud


def _create_items(crud: AutoCRUD, model, items, user="test"):
    mgr = crud.get_resource_manager(model)
    ids = []
    with mgr.meta_provide(user, dt.datetime(2025, 1, 1)):
        for item in items:
            info = mgr.create(item)
            ids.append(info.resource_id)
    return ids


def _dump_to_bytes(crud: AutoCRUD, **kw) -> bytes:
    bio = io.BytesIO()
    crud.dump(bio, **kw)
    return bio.getvalue()


def _load_from_bytes(crud: AutoCRUD, data: bytes, **kw):
    return crud.load(io.BytesIO(data), **kw)


# ============================================================================
# A. DumpStreamWriter / DumpStreamReader unit tests
# ============================================================================


class TestDumpStreamFormat:
    def test_roundtrip_header_eof(self):
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        w.write(HeaderRecord())
        w.write(EofRecord())

        bio.seek(0)
        r = DumpStreamReader(bio)
        records = list(r)
        assert len(records) == 2
        assert isinstance(records[0], HeaderRecord)
        assert records[0].version == 2
        assert isinstance(records[1], EofRecord)

    def test_roundtrip_all_record_types(self):
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        originals = [
            HeaderRecord(version=2),
            ModelStartRecord(model_name="item"),
            MetaRecord(data=b"meta_bytes"),
            RevisionRecord(data=b"revision_bytes"),
            BlobRecord(
                file_id="abc123",
                blob_data=b"\x00\x01\x02",
                size=3,
                content_type="application/octet-stream",
            ),
            ModelEndRecord(model_name="item"),
            EofRecord(),
        ]
        for rec in originals:
            w.write(rec)

        bio.seek(0)
        r = DumpStreamReader(bio)
        loaded = list(r)
        assert len(loaded) == len(originals)
        for orig, ld in zip(originals, loaded):
            assert type(orig) is type(ld)

        # Check BlobRecord fields in detail
        blob = loaded[4]
        assert isinstance(blob, BlobRecord)
        assert blob.file_id == "abc123"
        assert blob.blob_data == b"\x00\x01\x02"
        assert blob.size == 3

    def test_empty_stream(self):
        bio = io.BytesIO(b"")
        r = DumpStreamReader(bio)
        records = list(r)
        assert records == []

    def test_large_blob_roundtrip(self):
        big_data = b"\xab" * (2 * 1024 * 1024)  # 2 MB
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        w.write(
            BlobRecord(
                file_id="big",
                blob_data=big_data,
                size=len(big_data),
                content_type="bin",
            )
        )
        bio.seek(0)
        r = DumpStreamReader(bio)
        rec = next(r)
        assert isinstance(rec, BlobRecord)
        assert rec.blob_data == big_data

    def test_truncated_header_raises(self):
        bio = io.BytesIO(b"\x00\x00")  # only 2 bytes, need 4
        r = DumpStreamReader(bio)
        with pytest.raises(ValueError, match="Truncated frame header"):
            next(r)

    def test_truncated_payload_raises(self):
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        w.write(HeaderRecord())
        raw = bio.getvalue()
        # Keep the length prefix but truncate the payload
        truncated = raw[:6]
        r = DumpStreamReader(io.BytesIO(truncated))
        with pytest.raises(ValueError, match="Truncated frame payload"):
            next(r)


# ============================================================================
# B. BinaryProcessor.collect_file_ids unit tests
# ============================================================================


class TestBinaryProcessorCollect:
    def test_no_binary_fields(self):
        proc = BinaryProcessor(Item)
        result = proc.collect_file_ids(Item(name="a", value=1))
        assert result == set()

    def test_optional_binary_field(self):
        proc = BinaryProcessor(BlobItem)
        item = BlobItem(name="a", attachment=Binary(file_id="f1", size=10))
        result = proc.collect_file_ids(item)
        assert result == {"f1"}

    def test_optional_binary_none(self):
        proc = BinaryProcessor(BlobItem)
        item = BlobItem(name="a", attachment=None)
        result = proc.collect_file_ids(item)
        assert result == set()

    def test_list_binary_fields(self):
        proc = BinaryProcessor(NestedBlobItem)
        item = NestedBlobItem(
            name="a",
            files=[
                Binary(file_id="f1"),
                Binary(file_id="f2"),
            ],
        )
        result = proc.collect_file_ids(item)
        assert result == {"f1", "f2"}

    def test_dict_binary_fields(self):
        proc = BinaryProcessor(NestedBlobItem)
        item = NestedBlobItem(
            name="a",
            metadata={"x": Binary(file_id="f3"), "y": Binary(file_id="f4")},
        )
        result = proc.collect_file_ids(item)
        assert result == {"f3", "f4"}

    def test_binary_without_file_id(self):
        proc = BinaryProcessor(BlobItem)
        # Binary with UNSET file_id should not be collected
        item = BlobItem(name="a", attachment=Binary(data=b"hello"))
        result = proc.collect_file_ids(item)
        assert result == set()


# ============================================================================
# C. ResourceManager dump with QB
# ============================================================================


class TestResourceManagerDumpWithQB:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.crud = _make_crud(Item, indexed_fields=[("value", int)])
        self.mgr = self.crud.get_resource_manager(Item)
        self.ids = []
        with self.mgr.meta_provide("user", dt.datetime(2025, 1, 1)):
            for i in range(5):
                info = self.mgr.create(Item(name=f"item_{i}", value=i * 10))
                self.ids.append(info.resource_id)

    def test_dump_all(self):
        """Dump without query exports all 5 resources."""
        keys = [k for k, _ in self.mgr.dump()]
        meta_keys = [k for k in keys if k.startswith("meta/")]
        data_keys = [k for k in keys if k.startswith("data/")]
        assert len(meta_keys) == 5
        assert len(data_keys) == 5

    def test_dump_with_qb_filter(self):
        """Dump with QB filter exports only matching resources."""
        query = QB["value"] >= 30  # item_3 (30) and item_4 (40)
        keys = [k for k, _ in self.mgr.dump(query=query)]
        meta_keys = [k for k in keys if k.startswith("meta/")]
        assert len(meta_keys) == 2

    def test_dump_empty_storage(self):
        """Dump on empty storage yields nothing."""
        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        keys = [k for k, _ in mgr2.dump()]
        assert keys == []

    def test_dump_with_no_matches(self):
        """QB query that matches nothing yields empty."""
        query = QB["value"] >= 9999
        keys = [k for k, _ in self.mgr.dump(query=query)]
        assert keys == []

    def test_dump_with_multiple_revisions(self):
        """Resources with multiple revisions export all revisions."""
        rid = self.ids[0]
        with self.mgr.meta_provide("user", dt.datetime(2025, 1, 2)):
            self.mgr.update(rid, Item(name="item_0_v2", value=100))

        query = QB["resource_id"] == rid
        keys = [k for k, _ in self.mgr.dump(query=query)]
        meta_keys = [k for k in keys if k.startswith("meta/")]
        data_keys = [k for k in keys if k.startswith("data/")]
        assert len(meta_keys) == 1  # one meta per resource
        assert len(data_keys) == 2  # two revisions


# ============================================================================
# D. ResourceManager load with OnDuplicate
# ============================================================================


class TestResourceManagerLoadRecord:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.crud = _make_crud(Item)
        self.mgr = self.crud.get_resource_manager(Item)

    def _dump_records(self, mgr):
        """Collect dump output as (key, bytes) pairs."""
        return [(k, v.read()) for k, v in mgr.dump()]

    def test_load_overwrite(self):
        """Load on existing resource_id with OVERWRITE replaces meta."""
        with self.mgr.meta_provide("user", dt.datetime(2025, 1, 1)):
            info = self.mgr.create(Item(name="original", value=1))
        rid = info.resource_id

        # Create a separate source with the same resource_id (not feasible
        # directly, so we dump → modify → load)
        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        # Load the same data into crud2 first, then dump it
        records = self._dump_records(self.mgr)
        for key, data in records:
            mgr2.load(key, io.BytesIO(data))

        # Now load back into original with OVERWRITE - should succeed
        from autocrud.resource_manager.dump_format import MetaRecord

        for key, data in records:
            if key.startswith("meta/"):
                rec = MetaRecord(data=data)
                result = self.mgr.load_record(rec, OnDuplicate.overwrite)
                assert result is True

    def test_load_skip(self):
        """Load on existing resource_id with SKIP returns False."""
        with self.mgr.meta_provide("user", dt.datetime(2025, 1, 1)):
            self.mgr.create(Item(name="original", value=1))

        records = self._dump_records(self.mgr)
        from autocrud.resource_manager.dump_format import MetaRecord

        for key, data in records:
            if key.startswith("meta/"):
                rec = MetaRecord(data=data)
                result = self.mgr.load_record(rec, OnDuplicate.skip)
                assert result is False

    def test_load_raise(self):
        """Load on existing resource_id with RAISE_ERROR raises."""
        with self.mgr.meta_provide("user", dt.datetime(2025, 1, 1)):
            self.mgr.create(Item(name="original", value=1))

        records = self._dump_records(self.mgr)
        from autocrud.resource_manager.dump_format import MetaRecord

        for key, data in records:
            if key.startswith("meta/"):
                rec = MetaRecord(data=data)
                with pytest.raises(DuplicateResourceError):
                    self.mgr.load_record(rec, OnDuplicate.raise_error)

    def test_load_into_empty(self):
        """Load into empty storage always succeeds."""
        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)

        with self.mgr.meta_provide("user", dt.datetime(2025, 1, 1)):
            self.mgr.create(Item(name="a", value=1))

        records = self._dump_records(self.mgr)
        from autocrud.resource_manager.dump_format import (
            MetaRecord,
        )
        from autocrud.resource_manager.dump_format import (
            RevisionRecord as RR,
        )

        for key, data in records:
            if key.startswith("meta/"):
                assert mgr2.load_record(MetaRecord(data=data), OnDuplicate.raise_error)
            elif key.startswith("data/"):
                assert mgr2.load_record(RR(data=data), OnDuplicate.raise_error)


# ============================================================================
# E. AutoCRUD dump with model_queries
# ============================================================================


class TestAutoCRUDDump:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.crud = AutoCRUD()
        self.crud.add_model(Item, indexed_fields=[("value", int)])
        self.crud.add_model(Widget)
        _create_items(self.crud, Item, [Item("a", 1), Item("b", 2)])
        _create_items(self.crud, Widget, [Widget("w1"), Widget("w2"), Widget("w3")])

    def test_dump_all_models(self):
        """Dump without model_queries exports everything."""
        data = _dump_to_bytes(self.crud)
        assert len(data) > 0

        # Load into a fresh crud and verify counts
        crud2 = _make_crud(Item, Widget)
        stats = _load_from_bytes(crud2, data)
        assert "item" in stats
        assert "widget" in stats
        assert stats["item"].loaded == 2
        assert stats["widget"].loaded == 3

    def test_dump_single_model(self):
        """Dump only one model."""
        data = _dump_to_bytes(self.crud, model_queries={"item": None})

        crud2 = _make_crud(Item, Widget)
        stats = _load_from_bytes(crud2, data)
        assert "item" in stats
        assert stats["item"].loaded == 2
        assert "widget" not in stats

    def test_dump_with_qb_filter(self):
        """Dump filtered by QB on a single model."""
        data = _dump_to_bytes(
            self.crud,
            model_queries={"item": QB["value"] >= 2},
        )
        crud2 = AutoCRUD()
        crud2.add_model(Item, indexed_fields=[("value", int)])
        crud2.add_model(Widget)
        stats = _load_from_bytes(crud2, data)
        assert stats["item"].loaded == 1  # only "b" (value=2)

    def test_dump_unknown_model_raises(self):
        """Dumping an unregistered model raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            _dump_to_bytes(self.crud, model_queries={"nonexistent": None})

    def test_header_version(self):
        """Archive starts with a HeaderRecord v2."""
        data = _dump_to_bytes(self.crud)
        bio = io.BytesIO(data)
        r = DumpStreamReader(bio)
        first = next(r)
        assert isinstance(first, HeaderRecord)
        assert first.version == 2


# ============================================================================
# F. AutoCRUD load incremental
# ============================================================================


class TestAutoCRUDLoadIncremental:
    def test_load_overwrite_merges(self):
        """OVERWRITE: load into non-empty storage merges data."""
        crud1 = _make_crud(Item)
        ids1 = _create_items(crud1, Item, [Item("a", 1), Item("b", 2), Item("c", 3)])

        crud2 = _make_crud(Item)
        # Pre-populate crud2 with first 2 items
        partial_data = _dump_to_bytes(crud1, model_queries={"item": QB["value"] <= 2})
        _load_from_bytes(crud2, partial_data)

        # Now load all 3 items with OVERWRITE
        full_data = _dump_to_bytes(crud1)
        stats = _load_from_bytes(crud2, full_data, on_duplicate=OnDuplicate.overwrite)
        assert stats["item"].loaded == 3
        assert stats["item"].skipped == 0

        # Verify all 3 exist
        mgr2 = crud2.get_resource_manager(Item)
        for rid in ids1:
            assert mgr2.storage.exists(rid)

    def test_load_skip_preserves_existing(self):
        """SKIP: load into non-empty storage preserves existing data."""
        crud1 = _make_crud(Item)
        ids1 = _create_items(crud1, Item, [Item("a", 1), Item("b", 2)])

        crud2 = _make_crud(Item)
        # Pre-load first dump
        data1 = _dump_to_bytes(crud1)
        _load_from_bytes(crud2, data1)

        # Now re-load the same data with SKIP
        stats = _load_from_bytes(crud2, data1, on_duplicate=OnDuplicate.skip)
        assert stats["item"].skipped == 2
        assert stats["item"].loaded == 0

    def test_load_raise_on_duplicate(self):
        """RAISE: load into non-empty storage raises on first duplicate."""
        crud1 = _make_crud(Item)
        _create_items(crud1, Item, [Item("a", 1)])

        crud2 = _make_crud(Item)
        data = _dump_to_bytes(crud1)
        _load_from_bytes(crud2, data)

        # Re-load same data → should raise
        with pytest.raises(DuplicateResourceError):
            _load_from_bytes(crud2, data, on_duplicate=OnDuplicate.raise_error)


# ============================================================================
# G. Full roundtrip
# ============================================================================


class TestFullRoundtrip:
    def test_roundtrip_basic(self):
        """Dump and load produces identical data."""
        crud1 = _make_crud(Item, Widget)
        _create_items(crud1, Item, [Item("a", 1), Item("b", 2)])
        _create_items(crud1, Widget, [Widget("w1", 1.5)])

        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item, Widget)
        _load_from_bytes(crud2, data)

        # Dump crud2 and compare
        data2 = _dump_to_bytes(crud2)
        assert data == data2

    def test_roundtrip_with_revisions(self):
        """Resources with multiple revisions survive roundtrip."""
        crud1 = _make_crud(Item)
        ids = _create_items(crud1, Item, [Item("a", 1)])
        rid = ids[0]
        mgr1 = crud1.get_resource_manager(Item)
        with mgr1.meta_provide("user", dt.datetime(2025, 1, 2)):
            mgr1.update(rid, Item(name="a_v2", value=100))

        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, data)

        mgr2 = crud2.get_resource_manager(Item)
        revisions = mgr2.list_revisions(rid)
        assert len(revisions) == 2

    def test_roundtrip_with_soft_delete(self):
        """Soft-deleted resources survive roundtrip."""
        crud1 = _make_crud(Item)
        ids = _create_items(crud1, Item, [Item("a", 1)])
        rid = ids[0]
        mgr1 = crud1.get_resource_manager(Item)
        with mgr1.meta_provide("user", dt.datetime(2025, 1, 2)):
            mgr1.delete(rid)

        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, data)

        mgr2 = crud2.get_resource_manager(Item)
        meta = mgr2.storage.get_meta(rid)
        assert meta.is_deleted is True

    def test_roundtrip_empty(self):
        """Empty dump/load works correctly."""
        crud1 = _make_crud(Item)
        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item)
        stats = _load_from_bytes(crud2, data)
        assert stats["item"].loaded == 0


# ============================================================================
# H. Edge cases
# ============================================================================


class TestEdgeCases:
    def test_unknown_model_in_stream_raises(self):
        """Loading archive with unknown model raises ValueError."""
        crud1 = _make_crud(Item)
        _create_items(crud1, Item, [Item("a", 1)])
        data = _dump_to_bytes(crud1)

        crud2 = _make_crud(Widget)  # Does NOT have Item registered
        with pytest.raises(ValueError, match="not found"):
            _load_from_bytes(crud2, data)

    def test_invalid_header_version_raises(self):
        """Archive with wrong version raises ValueError."""
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        w.write(HeaderRecord(version=999))
        w.write(EofRecord())

        crud = _make_crud(Item)
        with pytest.raises(ValueError, match="Unsupported dump format version"):
            _load_from_bytes(crud, bio.getvalue())

    def test_missing_header_raises(self):
        """Archive not starting with HeaderRecord raises ValueError."""
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        w.write(ModelStartRecord(model_name="item"))
        w.write(EofRecord())

        crud = _make_crud(Item)
        with pytest.raises(ValueError, match="Expected HeaderRecord"):
            _load_from_bytes(crud, bio.getvalue())

    def test_load_stats_repr(self):
        s = LoadStats()
        s.loaded = 5
        s.skipped = 2
        s.total = 7
        assert "loaded=5" in repr(s)
        assert "skipped=2" in repr(s)

    def test_meta_record_outside_model_section(self):
        """MetaRecord without ModelStartRecord raises ValueError."""
        bio = io.BytesIO()
        w = DumpStreamWriter(bio)
        w.write(HeaderRecord())
        w.write(MetaRecord(data=b"some_data"))
        w.write(EofRecord())

        crud = _make_crud(Item)
        with pytest.raises(ValueError, match="outside of model section"):
            _load_from_bytes(crud, bio.getvalue())

    def test_dump_load_idempotent(self):
        """Dump → load → dump → load produces the same result."""
        crud1 = _make_crud(Item)
        _create_items(crud1, Item, [Item("x", 42)])

        d1 = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, d1)
        d2 = _dump_to_bytes(crud2)

        crud3 = _make_crud(Item)
        _load_from_bytes(crud3, d2)
        d3 = _dump_to_bytes(crud3)

        assert d2 == d3
