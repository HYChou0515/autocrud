"""Cross-store tests for ``iter_search`` over the new ``ResourceMeta.rev_*`` fields.

Each meta store implementation has its own filter-building code path (raw
SQL for sqlite/postgres, SQLAlchemy expressions for the SA store, pandas
``query`` for the dataframe store, in-memory ``is_match_query`` for the
memory/disk/redis stores). This module re-runs the same scenarios across
the parametrized matrix from ``ALL_META_STORE_TYPES`` so a regression in
any one store surfaces here.
"""

from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from specstar.query_types import (
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
)
from specstar.types import ResourceMeta, RevisionStatus

from .common import ALL_META_STORE_TYPES, get_meta_store


@pytest.fixture
def my_tmpdir():
    import tempfile

    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


def _make_meta(
    *,
    rev_status: RevisionStatus,
    rev_created_by: str,
    rev_updated_by: str,
    rev_created_time: dt.datetime,
    rev_updated_time: dt.datetime,
) -> ResourceMeta:
    rid = str(uuid.uuid4())
    base = dt.datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC"))
    return ResourceMeta(
        current_revision_id=f"{rid}:1",
        resource_id=rid,
        total_revision_count=1,
        created_time=base,
        updated_time=base,
        created_by="resource_owner",
        updated_by="resource_owner",
        is_deleted=False,
        rev_status=rev_status,
        rev_created_by=rev_created_by,
        rev_updated_by=rev_updated_by,
        rev_created_time=rev_created_time,
        rev_updated_time=rev_updated_time,
    )


@pytest.mark.flaky(retries=6, delay=1)
@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestRevIterSearch:
    @pytest.fixture(autouse=True)
    def setup_method(self, meta_store_type, my_tmpdir):
        self.meta_store = get_meta_store(meta_store_type, my_tmpdir)
        base_time = dt.datetime(2026, 1, 1, tzinfo=ZoneInfo("UTC"))

        self.alice_draft = _make_meta(
            rev_status=RevisionStatus.draft,
            rev_created_by="alice",
            rev_updated_by="alice",
            rev_created_time=base_time,
            rev_updated_time=base_time,
        )
        self.alice_stable = _make_meta(
            rev_status=RevisionStatus.stable,
            rev_created_by="alice",
            rev_updated_by="alice",
            rev_created_time=base_time + dt.timedelta(days=1),
            rev_updated_time=base_time + dt.timedelta(days=1),
        )
        self.bob_stable = _make_meta(
            rev_status=RevisionStatus.stable,
            rev_created_by="bob",
            rev_updated_by="bob",
            rev_created_time=base_time + dt.timedelta(days=10),
            rev_updated_time=base_time + dt.timedelta(days=10),
        )

        for meta in (self.alice_draft, self.alice_stable, self.bob_stable):
            self.meta_store[meta.resource_id] = meta

    def _ids(self, results):
        return sorted(m.resource_id for m in results)

    def test_filter_by_rev_status(self):
        q = ResourceMetaSearchQuery(rev_statuses=["draft"])
        ids = self._ids(self.meta_store.iter_search(q))
        assert ids == [self.alice_draft.resource_id]

    def test_filter_by_rev_created_by(self):
        q = ResourceMetaSearchQuery(rev_created_bys=["alice"])
        ids = self._ids(self.meta_store.iter_search(q))
        assert ids == sorted(
            [self.alice_draft.resource_id, self.alice_stable.resource_id]
        )

    def test_filter_by_rev_created_time_range(self):
        # Only the bob_stable record (10 days after base) matches >= base+5d
        q = ResourceMetaSearchQuery(
            rev_created_time_start=dt.datetime(2026, 1, 6, tzinfo=ZoneInfo("UTC")),
        )
        ids = self._ids(self.meta_store.iter_search(q))
        assert ids == [self.bob_stable.resource_id]

    def test_combined_status_and_creator(self):
        q = ResourceMetaSearchQuery(
            rev_statuses=["stable"],
            rev_created_bys=["alice"],
        )
        ids = self._ids(self.meta_store.iter_search(q))
        assert ids == [self.alice_stable.resource_id]

    def test_sort_by_rev_created_time_asc(self):
        q = ResourceMetaSearchQuery(
            sorts=[
                ResourceMetaSearchSort(
                    key=ResourceMetaSortKey.rev_created_time,
                    direction=ResourceMetaSortDirection.ascending,
                )
            ]
        )
        ids = [m.resource_id for m in self.meta_store.iter_search(q)]
        assert ids == [
            self.alice_draft.resource_id,
            self.alice_stable.resource_id,
            self.bob_stable.resource_id,
        ]
