"""The ``SetIndex`` annotation marker + its extraction (pure, no DB)."""

from typing import Annotated

import msgspec


def test_extract_set_index_fields_finds_marker_and_infers_element_type():
    from specstar.types import SetIndex, extract_set_index_field_infos

    class Foo(msgspec.Struct):
        keys: Annotated[list[str], SetIndex()]
        nums: Annotated[list[int], SetIndex()]
        plain: list[str]  # not declared → ignored

    infos = extract_set_index_field_infos(Foo)
    assert {i.name: i.elem_type for i in infos} == {"keys": str, "nums": int}


def test_set_index_nested_in_substruct_is_not_extracted_like_vector():
    # Aligns with Vector: extraction scans only top-level struct fields, so a
    # SetIndex nested inside a sub-struct is not picked up (no acceleration,
    # no error) — same reach as extract_vector_field_infos.
    from specstar.types import SetIndex, extract_set_index_field_infos

    class Inner(msgspec.Struct):
        keys: Annotated[list[str], SetIndex()]

    class Outer(msgspec.Struct):
        inner: Inner

    assert extract_set_index_field_infos(Outer) == []
