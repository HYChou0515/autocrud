"""Tests for Pydantic model Ref/DisplayName metadata preservation.

When a Pydantic BaseModel with Annotated[..., Ref(...)] fields is passed to
pydantic_to_struct(), the resulting msgspec Struct must preserve the Ref and
DisplayName metadata so that extract_refs() and extract_display_name() can
discover them for OpenAPI x-ref-* injection.

Bug: Pydantic v2 strips top-level Annotated metadata into FieldInfo.metadata,
so _iter_model_fields only returns fi.annotation (bare type without metadata).
This causes guild_id's Ref("guild") to be lost, while skill_ids' nested
Ref("skill") (inside list[Annotated[str, Ref("skill")]]) is preserved since
Pydantic doesn't unwrap nested Annotated.
"""

from typing import Annotated, Optional

import pytest

from autocrud.resource_manager.pydantic_converter import (
    _PYDANTIC_V2,
    pydantic_to_struct,
)
from autocrud.types import (
    DisplayName,
    OnDelete,
    Ref,
    RefRevision,
    extract_display_name,
    extract_refs,
)

requires_pydantic_v2 = pytest.mark.skipif(
    not _PYDANTIC_V2, reason="Requires Pydantic v2"
)


@requires_pydantic_v2
class TestPydanticRefMetadataPreservation:
    """pydantic_to_struct must preserve Ref/DisplayName metadata."""

    def test_ref_nullable_field_preserved(self):
        """Ref on a nullable field like guild_id: Annotated[str | None, Ref(...)]
        should be preserved after pydantic_to_struct conversion."""
        from pydantic import BaseModel

        class Character(BaseModel):
            name: str
            guild_id: Annotated[
                str | None, Ref("guild", on_delete=OnDelete.set_null)
            ] = None

        StructType = pydantic_to_struct(Character)
        refs = extract_refs(StructType, "character")

        assert len(refs) == 1
        ref = refs[0]
        assert ref.source == "character"
        assert ref.source_field == "guild_id"
        assert ref.target == "guild"
        assert ref.ref_type == "resource_id"
        assert ref.on_delete == OnDelete.set_null
        assert ref.nullable is True

    def test_ref_non_nullable_field_preserved(self):
        """Ref on a non-nullable field like owner_id: Annotated[str, Ref(...)]
        should be preserved."""
        from pydantic import BaseModel

        class Equipment(BaseModel):
            name: str
            owner_id: Annotated[str, Ref("character")]

        StructType = pydantic_to_struct(Equipment)
        refs = extract_refs(StructType, "equipment")

        assert len(refs) == 1
        ref = refs[0]
        assert ref.source_field == "owner_id"
        assert ref.target == "character"
        assert ref.on_delete == OnDelete.dangling

    def test_ref_list_field_preserved(self):
        """Ref inside list[Annotated[str, Ref(...)]] should still work
        (this already works but is here as a regression test)."""
        from pydantic import BaseModel

        class Character(BaseModel):
            name: str
            skill_ids: list[Annotated[str, Ref("skill")]] = []

        StructType = pydantic_to_struct(Character)
        refs = extract_refs(StructType, "character")

        assert len(refs) == 1
        ref = refs[0]
        assert ref.source_field == "skill_ids"
        assert ref.target == "skill"
        assert ref.is_list is True

    def test_multiple_refs_preserved(self):
        """Multiple Ref fields on a single model should all be preserved."""
        from pydantic import BaseModel

        class Character(BaseModel):
            name: str
            guild_id: Annotated[
                str | None, Ref("guild", on_delete=OnDelete.set_null)
            ] = None
            skill_ids: list[Annotated[str, Ref("skill")]] = []

        StructType = pydantic_to_struct(Character)
        refs = extract_refs(StructType, "character")

        assert len(refs) == 2
        ref_map = {r.source_field: r for r in refs}
        assert "guild_id" in ref_map
        assert ref_map["guild_id"].target == "guild"
        assert ref_map["guild_id"].on_delete == OnDelete.set_null
        assert "skill_ids" in ref_map
        assert ref_map["skill_ids"].target == "skill"

    def test_display_name_preserved(self):
        """DisplayName metadata should be preserved after pydantic_to_struct."""
        from pydantic import BaseModel

        class Guild(BaseModel):
            name: Annotated[str, DisplayName()]
            description: str = ""

        StructType = pydantic_to_struct(Guild)
        dn = extract_display_name(StructType)
        assert dn == "name"

    def test_ref_revision_preserved(self):
        """RefRevision metadata should be preserved."""
        from pydantic import BaseModel

        class Snapshot(BaseModel):
            name: str
            source_rev_id: Annotated[str | None, RefRevision("source")] = None

        StructType = pydantic_to_struct(Snapshot)
        refs = extract_refs(StructType, "snapshot")

        assert len(refs) == 1
        ref = refs[0]
        assert ref.source_field == "source_rev_id"
        assert ref.target == "source"
        assert ref.ref_type == "revision_id"

    def test_ref_and_display_name_together(self):
        """A model with both Ref and DisplayName on different fields."""
        from pydantic import BaseModel

        class Character(BaseModel):
            name: Annotated[str, DisplayName()]
            guild_id: Annotated[
                str | None, Ref("guild", on_delete=OnDelete.set_null)
            ] = None

        StructType = pydantic_to_struct(Character)

        # DisplayName
        dn = extract_display_name(StructType)
        assert dn == "name"

        # Ref
        refs = extract_refs(StructType, "character")
        assert len(refs) == 1
        assert refs[0].target == "guild"

    def test_ref_with_validators_preserved(self):
        """Ref metadata should be preserved even when validators are present."""
        from pydantic import BaseModel, field_validator

        class Character(BaseModel):
            name: Annotated[str, DisplayName()]
            guild_id: Annotated[
                str | None, Ref("guild", on_delete=OnDelete.set_null)
            ] = None

            @field_validator("name")
            @classmethod
            def name_not_empty(cls, v: str) -> str:
                if not v.strip():
                    raise ValueError("Name cannot be empty")
                return v

        StructType = pydantic_to_struct(Character)
        refs = extract_refs(StructType, "character")

        assert len(refs) == 1
        assert refs[0].source_field == "guild_id"
        assert refs[0].target == "guild"

    def test_nullable_ref_with_optional_syntax(self):
        """Ref with Optional[str] syntax (alternative to str | None)."""
        from pydantic import BaseModel

        class Character(BaseModel):
            name: str
            guild_id: Annotated[
                Optional[str], Ref("guild", on_delete=OnDelete.set_null)
            ] = None

        StructType = pydantic_to_struct(Character)
        refs = extract_refs(StructType, "character")

        assert len(refs) == 1
        ref = refs[0]
        assert ref.source_field == "guild_id"
        assert ref.target == "guild"
        assert ref.nullable is True
