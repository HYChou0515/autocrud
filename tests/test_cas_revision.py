"""#342 — optimistic concurrency on write paths.

A write that asserts a previous revision is atomic across workers: if another
worker moved the resource forward since you read it, the second writer gets a
``PreconditionFailedError`` instead of silently overwriting.

Covered here:
- ``rm.update(rid, data, expected_revision_id=rev)``
- ``rm.modify(rid, data, expected_revision_id=rev)``  (draft in-place edits)
- ``rm.create(data, resource_id=rid, if_not_exists=True)``  (atomic create-only)
"""

import msgspec
import pytest

from specstar import SpecStar
from specstar.errors import DuplicateResourceError, PreconditionFailedError
from specstar.types import RevisionStatus


class Doc(msgspec.Struct):
    name: str


def _rm():
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Doc, name="doc")
    return sp.get_resource_manager(Doc)


def test_update_with_matching_expected_revision_id_succeeds():
    rm = _rm()
    info = rm.create(Doc(name="v1"))
    new = rm.update(
        info.resource_id, Doc(name="v2"), expected_revision_id=info.revision_id
    )
    assert new.revision_id != info.revision_id  # produced a new revision


def test_update_with_stale_expected_revision_id_raises():
    # Worker A reads at rev 1. Worker B updates to rev 2. Worker A's expected
    # check fires — no overwrite.
    rm = _rm()
    info = rm.create(Doc(name="v1"))
    rm.update(info.resource_id, Doc(name="v2"))  # someone else moved it forward
    with pytest.raises(PreconditionFailedError) as ei:
        rm.update(
            info.resource_id, Doc(name="v3"), expected_revision_id=info.revision_id
        )
    # the error carries both ids for the caller to inspect / retry
    assert ei.value.expected_revision_id == info.revision_id
    assert ei.value.actual_revision_id != info.revision_id


def test_modify_with_stale_expected_revision_id_raises():
    # Same CAS guarantee on draft modify() — detects a concurrent revision bump.
    rm = _rm()
    info = rm.create(Doc(name="v1"), status=RevisionStatus.draft)
    rm.update(info.resource_id, Doc(name="v2"))  # concurrent forward move
    with pytest.raises(PreconditionFailedError):
        rm.modify(
            info.resource_id, Doc(name="v3"), expected_revision_id=info.revision_id
        )


def test_modify_with_matching_expected_revision_id_succeeds():
    rm = _rm()
    info = rm.create(Doc(name="v1"), status=RevisionStatus.draft)
    out = rm.modify(
        info.resource_id, Doc(name="v2"), expected_revision_id=info.revision_id
    )
    assert out.resource_id == info.resource_id


def test_create_if_not_exists_raises_when_resource_id_already_exists():
    # Atomic create-only — turns the silent-overwrite footgun into a clear
    # DuplicateResourceError, usable as a cross-worker mutex / first-wins lock.
    rm = _rm()
    info = rm.create(Doc(name="v1"))
    with pytest.raises(DuplicateResourceError):
        rm.create(
            Doc(name="loser"), resource_id=info.resource_id, if_not_exists=True
        )


def test_create_if_not_exists_succeeds_when_resource_id_is_new():
    rm = _rm()
    info = rm.create(Doc(name="v1"), resource_id="doc:fresh-1", if_not_exists=True)
    assert info.resource_id == "doc:fresh-1"


# --- in-place etag: detect concurrent modify() on the same revision_id ------


def test_revision_info_exposes_etag():
    rm = _rm()
    info = rm.create(Doc(name="x"))
    assert isinstance(info.etag, str)
    assert info.etag != info.revision_id  # includes the data hash too


def test_modify_with_stale_expected_etag_detects_concurrent_in_place_edit():
    # Two workers see the same draft revision; both want to modify in place.
    # expected_revision_id won't catch this (revision_id doesn't change on
    # modify). expected_etag does — it includes the data hash.
    rm = _rm()
    info = rm.create(Doc(name="v1"), status=RevisionStatus.draft)
    etag_at_read = info.etag

    # Worker B modifies first.
    rm.modify(info.resource_id, Doc(name="v2"), expected_etag=etag_at_read)
    # Worker A's etag is now stale even though revision_id hasn't moved.
    with pytest.raises(PreconditionFailedError):
        rm.modify(info.resource_id, Doc(name="v3"), expected_etag=etag_at_read)


def test_update_with_matching_expected_etag_succeeds():
    rm = _rm()
    info = rm.create(Doc(name="v1"))
    out = rm.update(info.resource_id, Doc(name="v2"), expected_etag=info.etag)
    assert out.resource_id == info.resource_id


def test_update_with_stale_expected_etag_raises():
    rm = _rm()
    info = rm.create(Doc(name="v1"))
    rm.update(info.resource_id, Doc(name="v2"))  # someone else moved forward
    with pytest.raises(PreconditionFailedError):
        rm.update(info.resource_id, Doc(name="v3"), expected_etag=info.etag)
