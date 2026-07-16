"""Reference semantics for the ``.any()`` element quantifier on a list field.

``QB["keys"].any()`` drops into "for SOME element, treated as a scalar string"
land, where every string operator recovers its ordinary scalar meaning:

- ``.any().eq("ol")``        -> some element **equals** "ol"      (membership)
- ``.any().contains("ol")``  -> some element **substring**-contains "ol"
- ``.any().regex("^ol$")``   -> some element matches, ``^``/``$`` anchored to
                                the single element (not the serialised array)

This is the composable, index-friendly answer to "find the card whose
``norm_keys`` has an element containing this substring", which the bare
``contains`` (exact membership) deliberately does NOT do.

This file pins the semantics on the pure-Python reference backends (memory /
disk). Cross-backend parity (sqlite / postgres push-down) lives in
``tests/meta_store/test_any_quantifier_parity.py``.
"""

import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from specstar.query import QB
from specstar.types import ResourceMeta
from tests.meta_store.common import get_meta_store


@pytest.fixture
def my_tmpdir():
    with tempfile.TemporaryDirectory(dir="./") as d:
        yield Path(d)


@pytest.mark.parametrize("meta_store_type", ["memory", "disk"])
class TestAnyQuantifier:
    # id -> keys (a list[str] indexed field)
    DATA = {
        "1": ["mol", "capping"],
        "2": ["m4", "m40"],
        "3": ["ol"],
        "4": [],  # empty list: never satisfies an existential
        "5": ["中文", "モル"],  # unicode parity
        "6": ["MOL"],  # uppercase, to separate contains from icontains
    }

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self.meta_store = get_meta_store(meta_store_type, my_tmpdir)
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        for rid, keys in self.DATA.items():
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

    def _ids(self, builder) -> list[str]:
        q = builder.build()
        return sorted(m.indexed_data["id"] for m in self.meta_store.iter_search(q))

    def test_contains_is_substring_over_elements(self):
        # "ol" is a substring of "mol" and of "ol" itself; "MOL" is uppercase so
        # a case-sensitive contains misses it.
        assert self._ids(QB["keys"].any().contains("ol")) == ["1", "3"]

    def test_eq_is_exact_membership_not_substring(self):
        # eq stays exact-element membership: only the literal "ol" element, NOT
        # "mol". This is the distinction bare .contains() already guarantees.
        assert self._ids(QB["keys"].any().eq("ol")) == ["3"]

    def test_contains_vs_eq_diverge_on_a_partial(self):
        # "4" is a substring of "m4"/"m40" but is no element on its own.
        assert self._ids(QB["keys"].any().contains("4")) == ["2"]
        assert self._ids(QB["keys"].any().eq("4")) == []

    def test_icontains_is_case_insensitive_substring(self):
        # adds the uppercase "MOL" row over the case-sensitive contains result.
        assert self._ids(QB["keys"].any().icontains("OL")) == ["1", "3", "6"]

    def test_starts_with_over_elements(self):
        # case-sensitive prefix: "mol", "m4", "m40" — not "MOL", not "モル".
        assert self._ids(QB["keys"].any().starts_with("m")) == ["1", "2"]

    def test_regex_is_anchored_per_element(self):
        # ^ol$ matches the element "ol" only — "mol" is NOT the whole element,
        # proving the anchors bind to a single element, not the array text.
        assert self._ids(QB["keys"].any().regex("^ol$")) == ["3"]

    def test_regex_suffix_over_elements(self):
        assert self._ids(QB["keys"].any().regex("ol$")) == ["1", "3"]

    def test_unicode_element_substring(self):
        assert self._ids(QB["keys"].any().contains("中")) == ["5"]

    def test_empty_list_never_matches(self):
        # row "4" (empty list) appears in no existential result.
        for b in (
            QB["keys"].any().contains("ol"),
            QB["keys"].any().eq("ol"),
            QB["keys"].any().regex(".*"),
        ):
            assert "4" not in self._ids(b)

    def test_all_is_universal_over_elements(self):
        # every element starts with "m": row 2 (m4, m40); row 4 (empty) matches
        # vacuously. Row 1 fails on "capping", row 6 on the uppercase "MOL".
        assert self._ids(QB["keys"].all().starts_with("m")) == ["2", "4"]

    def test_all_empty_list_matches_vacuously(self):
        # nothing satisfies "zzz", yet the empty-list row still matches all().
        assert self._ids(QB["keys"].all().contains("zzz")) == ["4"]
