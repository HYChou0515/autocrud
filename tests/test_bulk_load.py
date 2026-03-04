"""Tests for bulk load optimization.

Covers:
- MemoryResourceStore.save_many (loop-based fallback)
- SimpleStorage.save_revisions_bulk
- SimpleStorage.save_metas_bulk
- ResourceManager.load_records_bulk
- AutoCRUD.load uses bulk path
- Full roundtrip with bulk load
- on_duplicate strategies with bulk load
"""

from __future__ import annotations

import datetime as dt
import io

import pytest
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.resource_manager.dump_format import (
    BlobRecord,
    DumpStreamReader,
    MetaRecord,
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


def _get_records_by_type(data: bytes):
    """Parse dump data and return records grouped by type."""
    reader = DumpStreamReader(io.BytesIO(data))
    records = list(reader)
    metas = [r for r in records if isinstance(r, MetaRecord)]
    revisions = [r for r in records if isinstance(r, RevisionRecord)]
    blobs = [r for r in records if isinstance(r, BlobRecord)]
    return metas, revisions, blobs


# ============================================================================
# A. MemoryResourceStore.save_many
# ============================================================================


class TestMemoryResourceStoreSaveMany:
    def test_save_many_stores_revisions(self):
        """save_many writes all revisions to the store."""
        crud = _make_crud(Item)
        mgr = crud.get_resource_manager(Item)

        # Create some items, dump, collect revision data
        _create_items(crud, Item, [Item("a", 1), Item("b", 2)])
        data = _dump_to_bytes(crud)
        _, revisions, _ = _get_records_by_type(data)

        # Decode the revisions
        items_to_save = []
        for r in revisions:
            raw_res = mgr.resource_serializer.decode(r.data)
            items_to_save.append((raw_res.info, raw_res.raw_data))

        # save_many into a new ResourceStore
        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        store = mgr2.storage._resource_store
        store.save_many(items_to_save)

        # Verify all revisions are stored
        resource_ids = list(store.list_resources())
        assert len(resource_ids) == 2

    def test_save_many_empty_list(self):
        """save_many with empty list does nothing."""
        crud = _make_crud(Item)
        mgr = crud.get_resource_manager(Item)
        store = mgr.storage._resource_store
        store.save_many([])
        assert list(store.list_resources()) == []


# ============================================================================
# B. SimpleStorage bulk methods
# ============================================================================


class TestSimpleStorageBulk:
    def test_save_metas_bulk(self):
        """save_metas_bulk writes multiple metas at once."""
        crud = _make_crud(Item)
        mgr = crud.get_resource_manager(Item)

        # Create and dump
        _create_items(crud, Item, [Item("a", 1), Item("b", 2), Item("c", 3)])
        data = _dump_to_bytes(crud)
        metas, _, _ = _get_records_by_type(data)

        # Decode metas
        meta_objs = [mgr.meta_serializer.decode(r.data) for r in metas]

        # Bulk save into fresh storage
        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        mgr2.storage.save_metas_bulk(meta_objs)

        # Verify
        for m in meta_objs:
            assert mgr2.storage.exists(m.resource_id)

    def test_save_revisions_bulk(self):
        """save_revisions_bulk writes multiple revisions at once."""
        crud = _make_crud(Item)
        mgr = crud.get_resource_manager(Item)

        _create_items(crud, Item, [Item("a", 1), Item("b", 2)])
        data = _dump_to_bytes(crud)
        _, revisions, _ = _get_records_by_type(data)

        items_to_save = []
        for r in revisions:
            raw_res = mgr.resource_serializer.decode(r.data)
            items_to_save.append((raw_res.info, raw_res.raw_data))

        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        mgr2.storage.save_revisions_bulk(items_to_save)

        resource_ids = list(mgr2.storage._resource_store.list_resources())
        assert len(resource_ids) == 2


# ============================================================================
# C. ResourceManager.load_records_bulk
# ============================================================================


class TestResourceManagerLoadRecordsBulk:
    def test_load_records_bulk_overwrite(self):
        """load_records_bulk loads all records into storage."""
        crud = _make_crud(Item)
        _create_items(crud, Item, [Item("a", 1), Item("b", 2), Item("c", 3)])
        data = _dump_to_bytes(crud)
        metas, revisions, _ = _get_records_by_type(data)

        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        stats = mgr2.load_records_bulk(
            metas, revisions, [], on_duplicate=OnDuplicate.overwrite
        )
        assert stats.loaded == 3
        assert stats.total == 3
        assert stats.skipped == 0

        # Verify data
        for m in metas:
            meta = mgr2.meta_serializer.decode(m.data)
            assert mgr2.storage.exists(meta.resource_id)
            res = mgr2.get(meta.resource_id)
            assert isinstance(res.data, Item)

    def test_load_records_bulk_skip(self):
        """load_records_bulk with SKIP skips existing resources."""
        crud = _make_crud(Item)
        ids = _create_items(crud, Item, [Item("a", 1), Item("b", 2)])
        data = _dump_to_bytes(crud)
        metas, revisions, _ = _get_records_by_type(data)

        # Pre-load
        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, data)

        # Re-load with skip
        mgr2 = crud2.get_resource_manager(Item)
        stats = mgr2.load_records_bulk(
            metas, revisions, [], on_duplicate=OnDuplicate.skip
        )
        assert stats.skipped == 2
        assert stats.loaded == 0

    def test_load_records_bulk_raise_error(self):
        """load_records_bulk with RAISE_ERROR raises on duplicate."""
        crud = _make_crud(Item)
        _create_items(crud, Item, [Item("a", 1)])
        data = _dump_to_bytes(crud)
        metas, revisions, _ = _get_records_by_type(data)

        # Pre-load
        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, data)

        mgr2 = crud2.get_resource_manager(Item)
        with pytest.raises(DuplicateResourceError):
            mgr2.load_records_bulk(
                metas, revisions, [], on_duplicate=OnDuplicate.raise_error
            )

    def test_load_records_bulk_empty(self):
        """load_records_bulk with no records returns zero stats."""
        crud = _make_crud(Item)
        mgr = crud.get_resource_manager(Item)
        stats = mgr.load_records_bulk([], [], [], on_duplicate=OnDuplicate.overwrite)
        assert stats.loaded == 0
        assert stats.total == 0

    def test_load_records_bulk_with_revisions(self):
        """Resources with multiple revisions load correctly in bulk."""
        crud = _make_crud(Item)
        ids = _create_items(crud, Item, [Item("a", 1)])
        rid = ids[0]
        mgr = crud.get_resource_manager(Item)
        with mgr.meta_provide("user", dt.datetime(2025, 1, 2)):
            mgr.update(rid, Item(name="a_v2", value=100))

        data = _dump_to_bytes(crud)
        metas, revisions, _ = _get_records_by_type(data)
        assert len(revisions) == 2  # two revisions

        crud2 = _make_crud(Item)
        mgr2 = crud2.get_resource_manager(Item)
        stats = mgr2.load_records_bulk(
            metas, revisions, [], on_duplicate=OnDuplicate.overwrite
        )
        assert stats.loaded == 1

        # Verify both revisions exist
        rev_list = mgr2.list_revisions(rid)
        assert len(rev_list) == 2

    def test_load_records_bulk_fires_events(self):
        """Bulk load fires Before/After/OnSuccess events."""

        events_seen = []

        class SpyEventHandler:
            def is_supported(self, ctx):
                return True

            def handle_event(self, ctx):
                events_seen.append(type(ctx).__name__)

        crud = _make_crud(Item, event_handlers=[SpyEventHandler()])
        _create_items(crud, Item, [Item("a", 1)])
        data = _dump_to_bytes(crud)
        metas, revisions, _ = _get_records_by_type(data)

        crud2 = _make_crud(Item, event_handlers=[SpyEventHandler()])
        mgr2 = crud2.get_resource_manager(Item)
        events_seen.clear()
        mgr2.load_records_bulk(metas, revisions, [], on_duplicate=OnDuplicate.overwrite)

        # Should have Before and After load events
        assert any("BeforeLoad" in e for e in events_seen)
        assert any("AfterLoad" in e for e in events_seen)
        assert any("OnSuccessLoad" in e for e in events_seen)


# ============================================================================
# D. AutoCRUD.load uses bulk path
# ============================================================================


class TestAutoCRUDLoadBulk:
    def test_roundtrip_basic(self):
        """Dump → bulk load produces identical data."""
        crud1 = _make_crud(Item, Widget)
        _create_items(crud1, Item, [Item("a", 1), Item("b", 2)])
        _create_items(crud1, Widget, [Widget("w1", 1.5)])

        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item, Widget)
        stats = _load_from_bytes(crud2, data)

        assert stats["item"].loaded == 2
        assert stats["widget"].loaded == 1

        # Roundtrip consistency
        data2 = _dump_to_bytes(crud2)
        assert data == data2

    def test_roundtrip_with_revisions(self):
        """Resources with multiple revisions survive bulk load."""
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

    def test_load_overwrite_bulk(self):
        """OVERWRITE: bulk load into non-empty storage merges data."""
        crud1 = _make_crud(Item)
        ids = _create_items(crud1, Item, [Item("a", 1), Item("b", 2), Item("c", 3)])

        crud2 = _make_crud(Item)
        # Pre-populate with 2 items
        partial = _dump_to_bytes(crud1, model_queries={"item": None})
        _load_from_bytes(crud2, partial)

        # Re-load with overwrite
        stats = _load_from_bytes(crud2, partial, on_duplicate=OnDuplicate.overwrite)
        assert stats["item"].loaded == 3

    def test_load_skip_bulk(self):
        """SKIP: bulk load into non-empty storage skips existing."""
        crud1 = _make_crud(Item)
        _create_items(crud1, Item, [Item("a", 1), Item("b", 2)])
        data = _dump_to_bytes(crud1)

        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, data)

        stats = _load_from_bytes(crud2, data, on_duplicate=OnDuplicate.skip)
        assert stats["item"].skipped == 2
        assert stats["item"].loaded == 0

    def test_load_raise_bulk(self):
        """RAISE: bulk load raises on duplicate."""
        crud1 = _make_crud(Item)
        _create_items(crud1, Item, [Item("a", 1)])
        data = _dump_to_bytes(crud1)

        crud2 = _make_crud(Item)
        _load_from_bytes(crud2, data)

        with pytest.raises(DuplicateResourceError):
            _load_from_bytes(crud2, data, on_duplicate=OnDuplicate.raise_error)

    def test_load_soft_deleted(self):
        """Soft-deleted resources survive bulk load."""
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

    def test_load_empty(self):
        """Empty bulk load returns zero stats."""
        crud1 = _make_crud(Item)
        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item)
        stats = _load_from_bytes(crud2, data)
        assert stats["item"].loaded == 0

    def test_load_idempotent(self):
        """Dump → load → dump → load produces same result."""
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

    def test_load_multi_model(self):
        """Bulk load with multiple models works correctly."""
        crud1 = _make_crud(Item, Widget)
        _create_items(crud1, Item, [Item("a", 1), Item("b", 2)])
        _create_items(crud1, Widget, [Widget("w1"), Widget("w2"), Widget("w3")])

        data = _dump_to_bytes(crud1)
        crud2 = _make_crud(Item, Widget)
        stats = _load_from_bytes(crud2, data)

        assert stats["item"].loaded == 2
        assert stats["widget"].loaded == 3

        # Verify data integrity
        mgr_item = crud2.get_resource_manager(Item)
        mgr_widget = crud2.get_resource_manager(Widget)
        from autocrud.types import ResourceMetaSearchQuery

        q = ResourceMetaSearchQuery()
        assert mgr_item.count_resources(q) == 2
        assert mgr_widget.count_resources(q) == 3

    def test_load_with_blobs(self):
        """Bulk load with blob records works correctly."""
        crud1 = AutoCRUD()
        crud1.add_model(BlobItem)
        mgr1 = crud1.get_resource_manager(BlobItem)
        with mgr1.meta_provide("user", dt.datetime(2025, 1, 1)):
            mgr1.create(
                BlobItem(
                    name="doc",
                    attachment=Binary(data=b"hello world", content_type="text/plain"),
                )
            )

        data = _dump_to_bytes(crud1)
        crud2 = AutoCRUD()
        crud2.add_model(BlobItem)
        stats = _load_from_bytes(crud2, data)
        assert stats["blob-item"].loaded == 1

        # Verify blob data is accessible
        mgr2 = crud2.get_resource_manager(BlobItem)
        from autocrud.types import ResourceMetaSearchQuery as _Q

        metas = mgr2.search_resources(_Q())
        item = mgr2.get(metas[0].resource_id)
        assert item.data.attachment is not None
        assert item.data.attachment.file_id is not None
