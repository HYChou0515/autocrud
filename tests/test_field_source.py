"""``Field.source`` makes the QB convention real, not decorative.

Before this, ``QB["created_by"]`` and ``QB.created_by()`` both produced
``Field("created_by")`` with no source information, so when an indexed field
collided with a ``ResourceMeta`` attribute name, the runtime had to guess
(meta wins). With ``source``, the surface syntax actually picks the lookup:

- ``QB["foo"]``       → ``source="data"`` (indexed_data only)
- ``QB.created_by()`` → ``source="meta"`` (ResourceMeta only)
- bare ``Field("foo")`` → ``source="auto"`` (legacy: meta first, fallback data)
"""

from specstar.query import QB, Field


def test_subscript_marks_field_as_data():
    assert QB["source_doc_id"].source == "data"


def test_named_meta_method_marks_field_as_meta():
    assert QB.created_by().source == "meta"


def test_direct_field_construction_defaults_to_auto():
    assert Field("foo").source == "auto"


# --- slice 2: the aggregate API takes Field, not str ------------------------


import msgspec  # noqa: E402
import pytest  # noqa: E402

from specstar import Count, SpecStar, Sum  # noqa: E402
from specstar.aggregates import ForeignAggregate  # noqa: E402


class Chunk(msgspec.Struct):
    text: str
    source_doc_id: str


def _chunk_rm():
    sp = SpecStar()
    sp.configure(default_user="t")
    sp.add_model(Chunk, name="chunk", indexed_fields=[("source_doc_id", str)])
    return sp.get_resource_manager(Chunk)


def test_exp_aggregate_by_takes_field_for_by():
    rm = _chunk_rm()
    rm.create(Chunk(text="a", source_doc_id="d1"))
    rm.create(Chunk(text="b", source_doc_id="d1"))
    rm.create(Chunk(text="c", source_doc_id="d2"))
    rows = rm.exp_aggregate_by(QB["source_doc_id"], {"n": Count()})
    assert {r.key: r.n for r in rows} == {"d1": 2, "d2": 1}


def test_exp_aggregate_by_rejects_string_for_by():
    rm = _chunk_rm()
    with pytest.raises(TypeError, match="Field"):
        rm.exp_aggregate_by("source_doc_id", {"n": Count()})


def test_sum_takes_field_not_string():
    with pytest.raises(TypeError, match="Field"):
        Sum("size")


def test_foreign_aggregate_link_must_be_field():
    rm = _chunk_rm()
    with pytest.raises(TypeError, match="Field"):
        ForeignAggregate(rm, "source_doc_id", Count())


# --- slice 3: source-aware dispatch on collision -----------------------------
#
# A model field named ``created_by`` collides with the ResourceMeta audit field.
# Before, the runtime had to guess (meta won, silently). Now the surface picks
# the lookup: QB[\"created_by\"] -> indexed data, QB.created_by() -> meta.


class DocWithShadow(msgspec.Struct):
    created_by: str  # collides with ResourceMeta.created_by (the audit field)


def test_qb_subscript_reads_indexed_data_even_when_name_collides_with_meta():
    sp = SpecStar()
    sp.configure(default_user="audit-bob")
    sp.add_model(DocWithShadow, name="doc_shadow", indexed_fields=[("created_by", str)])
    rm = sp.get_resource_manager(DocWithShadow)
    # audit user "audit-bob" populates meta.created_by; the struct's created_by
    # populates indexed_data["created_by"] with a *different* value.
    rm.create(DocWithShadow(created_by="data-alice"))
    rm.create(DocWithShadow(created_by="data-alice"))

    rows = rm.exp_aggregate_by(QB["created_by"], {"n": Count()})
    assert {r.key: r.n for r in rows} == {"data-alice": 2}  # data wins


def test_qb_named_meta_method_reads_meta_attr_even_when_name_collides_with_indexed():
    sp = SpecStar()
    sp.configure(default_user="audit-bob")
    sp.add_model(
        DocWithShadow, name="doc_shadow2", indexed_fields=[("created_by", str)]
    )
    rm = sp.get_resource_manager(DocWithShadow)
    rm.create(DocWithShadow(created_by="data-alice"))
    rm.create(DocWithShadow(created_by="data-alice"))

    rows = rm.exp_aggregate_by(QB.created_by(), {"n": Count()})
    assert {r.key: r.n for r in rows} == {"audit-bob": 2}  # meta wins
