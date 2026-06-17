"""Cross-backend parity for the ``contains_any`` (list set-overlap) operator.

``QB["keys"].contains_any(values)`` matches rows whose list field ``keys``
shares at least one element with ``values`` (``set(keys) & set(values) != {}``)
— the "any-of" sibling of ``contains`` (single-element membership). It's the
indexable primitive the substring-dictionary use case reduces to: enumerate a
query's candidate substrings, then ``contains_any(candidates)``.

Every metastore implementation MUST return identical results — the SAME tests
run over ``ALL_META_STORE_TYPES``. Memory is the pure-Python reference; SQLite
and Postgres push it down to ``json_each`` / JSONB ``?|``.
"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from specstar.query import QB
from specstar.types import ResourceMeta

from .common import ALL_META_STORE_TYPES, get_meta_store


@pytest.fixture
def my_tmpdir():
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestContainsAny:
    # id -> keys (a list[str] indexed field)
    DATA = {
        "1": ["a", "b"],
        "2": ["b", "c"],
        "3": ["x"],
        "4": [],
        "5": ["中文", "良い"],  # CJK, to pin UTF-8 parity across backends
    }

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self.meta_store = get_meta_store(meta_store_type, my_tmpdir)
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        for i, (rid, keys) in enumerate(self.DATA.items()):
            meta = ResourceMeta(
                current_revision_id=f"rev_{rid}",
                resource_id=str(uuid.uuid4()),
                total_revision_count=1,
                created_time=base,
                updated_time=base,
                created_by="t",
                updated_by="t",
                is_deleted=False,
                indexed_data={"id": rid, "keys": keys},
            )
            self.meta_store[meta.resource_id] = meta

    def _ids(self, values) -> list[str]:
        q = QB["keys"].contains_any(values).build()
        return sorted(m.indexed_data["id"] for m in self.meta_store.iter_search(q))

    def test_overlap_matches_rows_sharing_an_element(self):
        # "a" is only in row 1's keys.
        assert self._ids(["a", "z"]) == ["1"]

    def test_matches_every_row_that_shares_any_element(self):
        # "b" is in rows 1 and 2; "x" is in row 3.
        assert self._ids(["b", "x"]) == ["1", "2", "3"]

    def test_no_overlap_returns_nothing(self):
        assert self._ids(["zzz", "qqq"]) == []

    def test_empty_candidates_match_nothing(self):
        assert self._ids([]) == []

    def test_empty_keys_row_never_matches(self):
        # Row 4 has keys=[]; it can't share an element with anything.
        assert "4" not in self._ids(["a", "b", "c", "x"])

    def test_cjk_elements_match_across_backends(self):
        # UTF-8 parity: the CJK element must compare equal on every backend.
        assert self._ids(["中文"]) == ["5"]
        assert self._ids(["良い", "a"]) == ["1", "5"]
