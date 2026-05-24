"""RFC 7386 merge-patch as a first-class ResourceManager operation.

``patch`` and ``modify`` already accept an RFC 6902 ``JsonPatch``; a
``MergePatch`` marker carries an RFC 7386 merge patch through the same methods,
so programmatic callers (and the HTTP layer) share one implementation.
"""

import datetime as dt

import msgspec

from specstar import Schema, SpecStar
from specstar.types import MergePatch


class Item(msgspec.Struct):
    qty: int = 0
    name: str = ""
    note: str | None = None


def _mgr():
    sp = SpecStar()
    sp.configure(
        default_user="t", default_now=lambda: dt.datetime.now(dt.timezone.utc)
    )
    sp.add_model(Schema(Item, "v1"))
    return sp.get_resource_manager(Item)


def test_manager_patch_accepts_merge_patch():
    mgr = _mgr()
    info0 = mgr.create(Item(qty=1, name="a"))
    info1 = mgr.patch(info0.resource_id, MergePatch({"qty": 50}))
    got = mgr.get(info0.resource_id).data
    assert got.qty == 50  # merged
    assert got.name == "a"  # preserved
    assert info1.revision_id != info0.revision_id  # new revision


def test_manager_merge_patch_null_deletes_field():
    mgr = _mgr()
    info0 = mgr.create(Item(qty=1, name="a", note="hi"))
    mgr.patch(info0.resource_id, MergePatch({"note": None}))
    assert mgr.get(info0.resource_id).data.note is None


def test_manager_modify_accepts_merge_patch():
    from specstar.types import RevisionStatus

    mgr = _mgr()
    info0 = mgr.create(Item(qty=1, name="a"), status=RevisionStatus.draft)
    info1 = mgr.modify(info0.resource_id, MergePatch({"qty": 50}))
    got = mgr.get(info0.resource_id).data
    assert got.qty == 50
    assert got.name == "a"
    # modify mutates the current (draft) revision in place — no new revision
    assert info1.revision_id == info0.revision_id
