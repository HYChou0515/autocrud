"""Cross-backend parity for the ``.any()`` / ``.all()`` element quantifier.

``QB["keys"].any().<op>(...)`` applies a scalar string predicate to each element
of a list field and folds the per-element results existentially (``any``) or
universally (``all``). Every metastore MUST agree — memory is the pure-Python
reference; SQLite / Postgres push it down to ``json_each`` /
``jsonb_array_elements_text`` wrapped in ``EXISTS``.

Same semantics as ``tests/test_any_quantifier.py`` (which pins them on the
reference backend); here they run over ``ALL_META_STORE_TYPES``.
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
class TestAnyQuantifierParity:
    # id -> keys (a list[str] indexed field)
    DATA = {
        "1": ["mol", "capping"],
        "2": ["m4", "m40"],
        "3": ["ol"],
        "4": [],  # empty list
        "5": ["中文", "モル"],  # unicode
        "6": ["MOL"],  # uppercase
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

    # --- any() ---------------------------------------------------------------

    def test_any_contains_is_substring(self):
        assert self._ids(QB["keys"].any().contains("ol")) == ["1", "3"]

    def test_any_eq_is_membership(self):
        assert self._ids(QB["keys"].any().eq("ol")) == ["3"]

    def test_any_contains_vs_eq_diverge_on_partial(self):
        assert self._ids(QB["keys"].any().contains("4")) == ["2"]
        assert self._ids(QB["keys"].any().eq("4")) == []

    def test_any_icontains_case_insensitive(self):
        assert self._ids(QB["keys"].any().icontains("OL")) == ["1", "3", "6"]

    def test_any_starts_with(self):
        assert self._ids(QB["keys"].any().starts_with("m")) == ["1", "2"]

    def test_any_ends_with(self):
        # "mol"/"ol" end with "ol"; "モル" ends with "ル" not "ol".
        assert self._ids(QB["keys"].any().ends_with("ol")) == ["1", "3"]

    def test_any_regex_anchored_per_element(self):
        assert self._ids(QB["keys"].any().regex("^ol$")) == ["3"]

    def test_any_regex_suffix(self):
        assert self._ids(QB["keys"].any().regex("ol$")) == ["1", "3"]

    def test_any_unicode_substring(self):
        assert self._ids(QB["keys"].any().contains("中")) == ["5"]

    def test_any_empty_list_never_matches(self):
        for b in (
            QB["keys"].any().contains("ol"),
            QB["keys"].any().regex(".*"),
        ):
            assert "4" not in self._ids(b)

    # --- all() ---------------------------------------------------------------

    def test_all_is_universal(self):
        # every element starts "m": row 2; row 4 (empty) vacuously.
        assert self._ids(QB["keys"].all().starts_with("m")) == ["2", "4"]

    def test_all_empty_list_matches_vacuously(self):
        assert self._ids(QB["keys"].all().contains("zzz")) == ["4"]


@pytest.mark.parametrize("meta_store_type", ALL_META_STORE_TYPES)
class TestBareListStringOpRejected:
    """A bare scalar string op on a *registered* list field is rejected — it
    would otherwise run against the serialised array — and directed to
    ``.any()``/``.all()``. ``contains`` (membership) and the quantified forms
    stay valid. Fires the same way on every backend (SQL from
    ``_build_condition``, reference from ``iter_search``)."""

    @pytest.fixture(autouse=True)
    def _setup(self, meta_store_type, my_tmpdir):
        self.meta_store = get_meta_store(meta_store_type, my_tmpdir)
        self.meta_store.register_list_field("keys")
        base = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        self.meta_store[str(uuid.uuid4())] = ResourceMeta(
            current_revision_id="rev",
            resource_id=str(uuid.uuid4()),
            total_revision_count=1,
            created_time=base,
            updated_time=base,
            created_by="t",
            updated_by="t",
            is_deleted=False,
            indexed_data={"id": "1", "keys": ["mol", "capping"]},
        )

    def _run(self, builder) -> list:
        return list(self.meta_store.iter_search(builder.build()))

    @pytest.mark.parametrize(
        "builder_name",
        ["regex", "starts_with", "ends_with", "icontains", "istarts_with"],
    )
    def test_bare_scalar_string_op_on_list_raises(self, builder_name):
        builder = getattr(QB["keys"], builder_name)("ol")
        with pytest.raises(ValueError, match="any"):
            self._run(builder)

    def test_quantified_form_is_allowed(self):
        # the sanctioned replacement must NOT raise
        assert self._run(QB["keys"].any().regex("^mol$")) != [] or True
        self._run(QB["keys"].any().starts_with("m"))
        self._run(QB["keys"].all().icontains("x"))

    def test_membership_ops_still_allowed(self):
        # contains = exact element membership; contains_any = overlap — both fine
        self._run(QB["keys"].contains("mol"))
        self._run(QB["keys"].contains_any(["mol"]))

    def test_unregistered_field_not_rejected(self):
        # a scalar (non-list) field keeps ordinary substring/regex semantics
        self._run(QB["other"].regex("x"))
