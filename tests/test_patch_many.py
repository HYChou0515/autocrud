"""`ResourceManager.patch_many` — one patch, many rows (issue #434).

The shape is deliberately *patch*, not *update*: a caller pushing a derived
mirror onto every row of a collection should describe the fields that change,
not read every row out, edit three fields, and write the whole thing back. The
read then belongs to specstar, which is the only layer that can batch it.

Semantically this is "N patches, whose reads and writes go through the bulk
path" — **not** a new set of rules. In particular events fire per row, because
that is where write ACLs live: firing once per batch would let a bulk call
walk straight past a per-row permission check.
"""

from __future__ import annotations

import datetime as dt

from msgspec import Struct

from specstar.crud.core import SpecStar
from specstar.permission.checker import IPermissionChecker, PermissionResult
from specstar.query import QB
from specstar.resource_manager.core import PermissionEventHandler
from specstar.types import MergePatch, ResourceAction

_NOW = dt.datetime(2026, 7, 20, tzinfo=dt.timezone.utc)


class Doc(Struct):
    name: str
    collection_id: str
    visibility: str = "private"
    body: str = ""


def _spec(**kw):
    spec = SpecStar(**kw)
    spec.configure(default_user="owner", default_now=lambda: _NOW)
    return spec


def _seeded(n=3, collection="c1", **kw):
    spec = _spec(**kw)
    spec.add_model(Doc, indexed_fields=["collection_id", "visibility"])
    rm = spec.get_resource_manager(Doc)
    ids = [
        rm.create(Doc(name=f"d{i}", collection_id=collection)).resource_id
        for i in range(n)
    ]
    return rm, ids


def _in(collection: str):
    return (QB["collection_id"] == collection).build()


# ---------------------------------------------------------------------------
# The fan-out this exists for
# ---------------------------------------------------------------------------


def test_patch_many_pushes_one_patch_onto_every_matching_row():
    rm, ids = _seeded(3)

    result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert result.patched == 3
    assert all(rm.get(rid).data.visibility == "public" for rid in ids)


def test_patch_many_leaves_other_fields_alone():
    """A merge patch names the fields that change; the rest must survive."""
    rm, ids = _seeded(2)
    rm.update(ids[0], Doc(name="kept", collection_id="c1", body="important"))

    rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    doc = rm.get(ids[0]).data
    assert (doc.name, doc.body, doc.visibility) == ("kept", "important", "public")


def test_patch_many_only_touches_rows_the_query_selected():
    rm, ids = _seeded(2, collection="c1")
    other = rm.create(Doc(name="elsewhere", collection_id="c2")).resource_id

    result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert result.patched == 2
    assert rm.get(other).data.visibility == "private"


def test_patch_many_on_an_empty_selection_does_nothing():
    rm, _ = _seeded(2)

    result = rm.patch_many(_in("nope"), MergePatch({"visibility": "public"}))

    assert (result.patched, result.unchanged) == (0, 0)
    assert result.failures == [] and result.conflicts == []


# ---------------------------------------------------------------------------
# No-op patches must not churn revisions
# ---------------------------------------------------------------------------


def test_a_row_already_holding_the_target_value_is_reported_unchanged():
    """The caller should not have to pre-filter to avoid churning revisions.

    `update` already short-circuits when the encoded data hashes the same, so
    a re-run of a fan-out is nearly free — but "how many rows did this change"
    is still the number the caller reports, so the two counts stay separate.
    """
    rm, ids = _seeded(3)
    rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert (result.patched, result.unchanged) == (0, 3)


def test_a_no_op_patch_creates_no_new_revision():
    rm, ids = _seeded(1)
    before = len(rm.list_revisions(ids[0]))

    rm.patch_many(_in("c1"), MergePatch({"visibility": "private"}))

    assert len(rm.list_revisions(ids[0])) == before


# ---------------------------------------------------------------------------
# Per-row permission — the reason events are not fired once per batch
# ---------------------------------------------------------------------------


class _DenyOne(IPermissionChecker):
    """Denies writes to one specific row, allows everything else.

    Models the real shape of a per-row write ACL: the verdict depends on the
    row being written, so it cannot be decided once for a whole batch.
    """

    def __init__(self, denied_id: str) -> None:
        self.denied_id = denied_id
        self.seen: list[str | None] = []

    def required_resource_parts(self, action) -> frozenset:
        return frozenset()

    def check_permission(self, context) -> PermissionResult:
        if getattr(context, "action", None) is not ResourceAction.patch:
            return PermissionResult.allow
        rid = getattr(context, "resource_id", None)
        self.seen.append(rid)
        if rid == self.denied_id:
            return PermissionResult.deny
        return PermissionResult.allow


def _with_checker(denied_index=1, n=3):
    spec = _spec()
    rm_probe = None
    spec.add_model(Doc, indexed_fields=["collection_id", "visibility"])
    rm = spec.get_resource_manager(Doc)
    ids = [
        rm.create(Doc(name=f"d{i}", collection_id="c1")).resource_id for i in range(n)
    ]
    checker = _DenyOne(ids[denied_index])
    rm.event_handlers = [PermissionEventHandler(checker)]
    return rm, ids, checker, rm_probe


def test_the_permission_check_runs_for_every_row():
    """Firing events once per batch would authorize the batch, not the rows.

    A bulk path that skipped this would be a way to write rows the caller is
    not allowed to write — the batch equivalent of an unchecked endpoint.
    """
    rm, ids, checker, _ = _with_checker()

    rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert sorted(checker.seen) == sorted(ids)


def test_a_denied_row_is_reported_and_not_written():
    rm, ids, checker, _ = _with_checker(denied_index=1)

    result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert result.patched == 2
    assert [rid for rid, _ in result.failures] == [ids[1]]
    assert rm.get(ids[1]).data.visibility == "private"


def test_a_denied_row_does_not_stop_the_others():
    """Collect-and-continue: one bad row must not strand the rest of a
    collection's permission fan-out."""
    rm, ids, checker, _ = _with_checker(denied_index=0)

    rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert rm.get(ids[1]).data.visibility == "public"
    assert rm.get(ids[2]).data.visibility == "public"


# ---------------------------------------------------------------------------
# Optimistic concurrency
# ---------------------------------------------------------------------------


def test_a_row_that_moved_since_selection_is_a_conflict_not_a_clobber():
    """The window between selecting rows and writing them is long in a
    fan-out. Writing anyway would silently discard the concurrent edit — the
    whole row, not just the mirrored fields, because a patch rewrites the
    whole body.
    """
    rm, ids = _seeded(3)
    victim = ids[1]

    original = rm.storage.read_revisions_bulk

    def _racing(items, *, max_bytes):
        out = original(items, max_bytes=max_bytes)
        # A concurrent writer lands after we read, before we write.
        if any(rid == victim for rid, _, _ in items):
            rm.update(victim, Doc(name="edited by someone else", collection_id="c1"))
        return out

    rm.storage.read_revisions_bulk = _racing
    try:
        result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))
    finally:
        rm.storage.read_revisions_bulk = original

    assert result.conflicts == [victim]
    assert result.patched == 2
    assert rm.get(victim).data.name == "edited by someone else"


# ---------------------------------------------------------------------------
# Memory budget
# ---------------------------------------------------------------------------


def test_patch_many_covers_every_row_across_several_batches():
    """A budget smaller than the selection must not silently truncate it."""
    rm, ids = _seeded(5)

    result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}), max_bytes=1)

    assert result.patched == 5
    assert all(rm.get(rid).data.visibility == "public" for rid in ids)


def test_the_budget_bounds_how_much_is_held_at_once():
    rm, ids = _seeded(4)
    sizes: list[int] = []

    original = rm.storage.read_revisions_bulk

    def _recording(items, *, max_bytes):
        payloads, consumed = original(items, max_bytes=max_bytes)
        sizes.append(sum(len(v) for v in payloads.values()))
        return payloads, consumed

    rm.storage.read_revisions_bulk = _recording
    try:
        rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}), max_bytes=1)
    finally:
        rm.storage.read_revisions_bulk = original

    # One row per batch — the budget is below a single row, and the primitive
    # guarantees at least one so it still makes progress.
    assert len(sizes) == 4


def test_a_row_bigger_than_the_whole_budget_is_still_patched():
    rm, ids = _seeded(1)
    rm.update(ids[0], Doc(name="big", collection_id="c1", body="x" * 10_000))

    result = rm.patch_many(
        _in("c1"), MergePatch({"visibility": "public"}), max_bytes=10
    )

    assert result.patched == 1
    assert rm.get(ids[0]).data.visibility == "public"


# ---------------------------------------------------------------------------
# The selection is the query's, limit and all
# ---------------------------------------------------------------------------


def test_a_query_limit_bounds_the_fan_out_and_the_report_says_so():
    """`patch_many` patches what the query selects — including its `limit`.

    That matters because the default limit is configurable process-wide, so a
    deployment could cap it without this call site knowing. The cap must not
    be *silent*: `total` reports how many rows were actually selected, so a
    caller that expected more can tell the difference between "nothing to do"
    and "I was truncated".
    """
    rm, ids = _seeded(5)
    query = (QB["collection_id"] == "c1").build()
    query.limit = 2

    result = rm.patch_many(query, MergePatch({"visibility": "public"}))

    assert result.patched == 2
    assert result.total == 2
    assert sum(rm.get(rid).data.visibility == "public" for rid in ids) == 2


def test_total_accounts_for_every_selected_row():
    rm, ids, checker, _ = _with_checker(denied_index=0, n=3)

    result = rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}))

    assert result.total == 3
    assert result.patched == 2 and len(result.failures) == 1


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_patch_many_records_the_acting_user_as_the_updater():
    rm, ids = _seeded(2)

    rm.patch_many(_in("c1"), MergePatch({"visibility": "public"}), user="fanout-bot")

    meta = rm.get_meta(ids[0])
    assert meta.updated_by == "fanout-bot"
    assert meta.created_by == "owner"  # the row keeps its own creator
