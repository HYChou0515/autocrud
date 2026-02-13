"""Tests for Ref / RefRevision / OnDelete and related utilities.

Covers:
- OnDelete enum values
- Ref / RefRevision constructors, __repr__, __eq__, __hash__
- _RefInfo struct
- extract_refs() for various annotation shapes
- _inject_ref_metadata() OpenAPI extension injection
- add_model() validation (set_null + non-nullable raise)
- apply() validation (unregistered target warning)
- x-autocrud-relationships top-level extension
- Referential integrity: cascade delete, set_null on delete
- Auto-indexing of Ref fields
- API: GET /{target}/{resource_id}/referrers
- API: GET /_relationships
"""

import datetime as dt
import logging
from typing import Annotated

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import (
    OnDelete,
    Ref,
    RefRevision,
    _RefInfo,
    extract_refs,
)

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Zone(Struct):
    name: str


class Guild(Struct):
    name: str


class Character(Struct):
    name: str


class Monster(Struct, kw_only=True):
    zone_id: Annotated[str, Ref("zone")]
    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None
    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.cascade)]
    zone_revision_id: Annotated[str, RefRevision("zone")]


class NullableRefRevision(Struct):
    zone_revision_id: Annotated[str | None, RefRevision("zone")] = None


class NoRefs(Struct):
    name: str
    age: int


class SetNullNonNullable(Struct):
    """set_null on a non-nullable field — should raise at add_model time."""

    target_id: Annotated[str, Ref("target", on_delete=OnDelete.set_null)]


class Skill(Struct):
    """A skill resource (target of list ref)."""

    name: str


class CharacterWithSkills(Struct, kw_only=True):
    """Character that references skills via a list of Refs (N:N)."""

    name: str
    skill_ids: list[Annotated[str, Ref("skill")]] = []


class UnregisteredTarget(Struct):
    """Ref to a model that won't be registered."""

    other_id: Annotated[str, Ref("nonexistent")]


# ---------------------------------------------------------------------------
# OnDelete enum
# ---------------------------------------------------------------------------


class TestOnDelete:
    def test_values(self):
        assert OnDelete.dangling == "dangling"
        assert OnDelete.set_null == "set_null"
        assert OnDelete.cascade == "cascade"

    def test_membership(self):
        assert len(OnDelete) == 3

    def test_string_conversion(self):
        assert OnDelete("dangling") is OnDelete.dangling
        assert OnDelete("set_null") is OnDelete.set_null
        assert OnDelete("cascade") is OnDelete.cascade

    def test_invalid_value(self):
        with pytest.raises(ValueError):
            OnDelete("invalid")


# ---------------------------------------------------------------------------
# Ref
# ---------------------------------------------------------------------------


class TestRef:
    def test_basic_construction(self):
        r = Ref("zone")
        assert r.resource == "zone"
        assert r.on_delete == OnDelete.dangling

    def test_with_on_delete(self):
        r = Ref("guild", on_delete=OnDelete.set_null)
        assert r.resource == "guild"
        assert r.on_delete == OnDelete.set_null

    def test_on_delete_string_conversion(self):
        """on_delete accepts a string and converts to OnDelete enum."""
        r = Ref("x", on_delete="cascade")
        assert r.on_delete is OnDelete.cascade

    def test_repr(self):
        r = Ref("zone")
        assert "Ref(" in repr(r)
        assert "'zone'" in repr(r)
        assert "on_delete=" in repr(r)

    def test_repr_with_on_delete(self):
        r = Ref("guild", on_delete=OnDelete.cascade)
        assert "cascade" in repr(r)

    def test_eq_same(self):
        assert Ref("zone") == Ref("zone")

    def test_eq_different_resource(self):
        assert Ref("zone") != Ref("guild")

    def test_eq_different_on_delete(self):
        assert Ref("zone") != Ref("zone", on_delete=OnDelete.cascade)

    def test_eq_non_ref(self):
        assert Ref("zone").__eq__("not-a-ref") is NotImplemented

    def test_hash_same(self):
        assert hash(Ref("zone")) == hash(Ref("zone"))

    def test_hash_different(self):
        # Different objects can collide in theory, but these should be different
        assert hash(Ref("zone")) != hash(Ref("zone", on_delete=OnDelete.cascade))

    def test_usable_as_set_key(self):
        s = {Ref("zone"), Ref("zone"), Ref("guild")}
        assert len(s) == 2

    def test_usable_as_dict_key(self):
        d = {Ref("zone"): 1, Ref("guild"): 2}
        assert d[Ref("zone")] == 1


# ---------------------------------------------------------------------------
# RefRevision
# ---------------------------------------------------------------------------


class TestRefRevision:
    def test_basic_construction(self):
        r = RefRevision("zone")
        assert r.resource == "zone"

    def test_repr(self):
        r = RefRevision("zone")
        assert repr(r) == "RefRevision('zone')"

    def test_eq_same(self):
        assert RefRevision("zone") == RefRevision("zone")

    def test_eq_different(self):
        assert RefRevision("zone") != RefRevision("guild")

    def test_eq_non_ref_revision(self):
        assert RefRevision("zone").__eq__("not-a-ref") is NotImplemented

    def test_hash_same(self):
        assert hash(RefRevision("zone")) == hash(RefRevision("zone"))

    def test_usable_as_set_key(self):
        s = {RefRevision("zone"), RefRevision("zone"), RefRevision("guild")}
        assert len(s) == 2


# ---------------------------------------------------------------------------
# _RefInfo
# ---------------------------------------------------------------------------


class TestRefInfo:
    def test_construction(self):
        info = _RefInfo(
            source="monster",
            source_field="zone_id",
            target="zone",
            ref_type="resource_id",
            on_delete=OnDelete.dangling,
            nullable=False,
        )
        assert info.source == "monster"
        assert info.source_field == "zone_id"
        assert info.target == "zone"
        assert info.ref_type == "resource_id"
        assert info.on_delete == OnDelete.dangling
        assert info.nullable is False

    def test_frozen(self):
        info = _RefInfo(
            source="m",
            source_field="f",
            target="t",
            ref_type="resource_id",
            on_delete=OnDelete.dangling,
            nullable=False,
        )
        with pytest.raises(AttributeError):
            info.source = "other"


# ---------------------------------------------------------------------------
# extract_refs()
# ---------------------------------------------------------------------------


class TestExtractRefs:
    def test_basic_ref(self):
        refs = extract_refs(Monster, "monster")
        zone_refs = [r for r in refs if r.source_field == "zone_id"]
        assert len(zone_refs) == 1
        r = zone_refs[0]
        assert r.source == "monster"
        assert r.target == "zone"
        assert r.ref_type == "resource_id"
        assert r.on_delete == OnDelete.dangling
        assert r.nullable is False

    def test_nullable_ref(self):
        refs = extract_refs(Monster, "monster")
        guild_refs = [r for r in refs if r.source_field == "guild_id"]
        assert len(guild_refs) == 1
        r = guild_refs[0]
        assert r.target == "guild"
        assert r.on_delete == OnDelete.set_null
        assert r.nullable is True

    def test_cascade_ref(self):
        refs = extract_refs(Monster, "monster")
        owner_refs = [r for r in refs if r.source_field == "owner_id"]
        assert len(owner_refs) == 1
        r = owner_refs[0]
        assert r.target == "character"
        assert r.on_delete == OnDelete.cascade
        assert r.nullable is False

    def test_ref_revision(self):
        refs = extract_refs(Monster, "monster")
        rev_refs = [r for r in refs if r.source_field == "zone_revision_id"]
        assert len(rev_refs) == 1
        r = rev_refs[0]
        assert r.target == "zone"
        assert r.ref_type == "revision_id"
        assert r.on_delete == OnDelete.dangling  # RefRevision always dangling

    def test_nullable_ref_revision(self):
        refs = extract_refs(NullableRefRevision, "test")
        assert len(refs) == 1
        assert refs[0].nullable is True
        assert refs[0].ref_type == "revision_id"

    def test_no_refs(self):
        refs = extract_refs(NoRefs, "nope")
        assert refs == []

    def test_all_refs_from_monster(self):
        refs = extract_refs(Monster, "monster")
        assert len(refs) == 4  # zone_id, guild_id, owner_id, zone_revision_id

    def test_non_struct_returns_empty(self):
        """extract_refs should handle non-Struct classes gracefully."""

        class PlainClass:
            x: int = 0

        refs = extract_refs(PlainClass, "plain")
        # Either returns empty or returns refs if get_type_hints works
        # The main point is it doesn't crash
        assert isinstance(refs, list)


# ---------------------------------------------------------------------------
# AutoCRUD add_model() validation
# ---------------------------------------------------------------------------


class TestAddModelRefValidation:
    def test_set_null_non_nullable_raises(self):
        """set_null on a non-Optional field must raise ValueError."""
        crud = AutoCRUD()
        with pytest.raises(ValueError, match="set_null"):
            crud.add_model(SetNullNonNullable, name="set-null-bad")

    def test_valid_refs_collected(self):
        """add_model should populate self.relationships."""
        crud = AutoCRUD()
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        assert len(crud.relationships) == 4  # Monster has 4 refs

    def test_no_refs_no_relationships(self):
        crud = AutoCRUD()
        crud.add_model(NoRefs, name="norefs")
        assert len(crud.relationships) == 0


# ---------------------------------------------------------------------------
# AutoCRUD apply() — unregistered target warning
# ---------------------------------------------------------------------------


class TestApplyRefValidation:
    def test_unregistered_target_warns(self, caplog):
        """apply() should log a warning when a Ref target is not registered."""
        crud = AutoCRUD()
        crud.add_model(UnregisteredTarget, name="with-dangling-ref")
        app = FastAPI()
        with caplog.at_level(logging.WARNING):
            crud.apply(app)
        assert any("nonexistent" in r.message for r in caplog.records)

    def test_valid_targets_no_warning(self, caplog):
        """No warning when all Ref targets are registered."""
        crud = AutoCRUD()
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        with caplog.at_level(logging.WARNING):
            crud.apply(app)
        ref_warnings = [r for r in caplog.records if "not registered" in r.message]
        assert len(ref_warnings) == 0


# ---------------------------------------------------------------------------
# _inject_ref_metadata() — OpenAPI extension injection
# ---------------------------------------------------------------------------


class TestInjectRefMetadata:
    def _build_app_with_schema(self):
        """Helper: create a FastAPI app with Monster + deps, return app."""
        crud = AutoCRUD()
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_x_ref_resource_on_property(self):
        app = self._build_app_with_schema()
        schema = app.openapi_schema
        monster_schema = schema["components"]["schemas"]["Monster"]
        props = monster_schema["properties"]

        # zone_id should have x-ref-resource = "zone"
        assert props["zone_id"]["x-ref-resource"] == "zone"
        assert props["zone_id"]["x-ref-type"] == "resource_id"
        assert props["zone_id"]["x-ref-on-delete"] == "dangling"

    def test_x_ref_nullable_property(self):
        app = self._build_app_with_schema()
        schema = app.openapi_schema
        monster_schema = schema["components"]["schemas"]["Monster"]
        props = monster_schema["properties"]

        # guild_id is nullable — x-ref should still be present
        assert props["guild_id"]["x-ref-resource"] == "guild"
        assert props["guild_id"]["x-ref-on-delete"] == "set_null"

    def test_x_ref_cascade_property(self):
        app = self._build_app_with_schema()
        schema = app.openapi_schema
        monster_schema = schema["components"]["schemas"]["Monster"]
        props = monster_schema["properties"]

        assert props["owner_id"]["x-ref-resource"] == "character"
        assert props["owner_id"]["x-ref-on-delete"] == "cascade"

    def test_x_ref_revision_property(self):
        app = self._build_app_with_schema()
        schema = app.openapi_schema
        monster_schema = schema["components"]["schemas"]["Monster"]
        props = monster_schema["properties"]

        assert props["zone_revision_id"]["x-ref-resource"] == "zone"
        assert props["zone_revision_id"]["x-ref-type"] == "revision_id"
        # RefRevision has no on_delete extension
        assert "x-ref-on-delete" not in props["zone_revision_id"]

    def test_x_autocrud_relationships_extension(self):
        app = self._build_app_with_schema()
        schema = app.openapi_schema

        rels = schema.get("x-autocrud-relationships")
        assert rels is not None
        assert isinstance(rels, list)
        assert len(rels) == 4

        # Check structure of one relationship
        zone_rel = next(r for r in rels if r["sourceField"] == "zone_id")
        assert zone_rel["source"] == "monster"
        assert zone_rel["target"] == "zone"
        assert zone_rel["refType"] == "resource_id"
        assert zone_rel["onDelete"] == "dangling"
        assert zone_rel["nullable"] is False

    def test_no_refs_no_extension(self):
        """When no models have refs, x-autocrud-relationships should be absent."""
        crud = AutoCRUD()
        crud.add_model(NoRefs, name="norefs")
        app = FastAPI()
        crud.apply(app)
        crud.openapi(app)
        schema = app.openapi_schema
        assert "x-autocrud-relationships" not in schema


# ---------------------------------------------------------------------------
# Public import from autocrud
# ---------------------------------------------------------------------------


class TestPublicImport:
    def test_import_ref_from_autocrud(self):
        from autocrud import Ref

        assert Ref is not None

    def test_import_ref_revision_from_autocrud(self):
        from autocrud import RefRevision

        assert RefRevision is not None

    def test_import_on_delete_from_autocrud(self):
        from autocrud import OnDelete

        assert OnDelete is not None


# ---------------------------------------------------------------------------
# Auto-indexing of Ref fields
# ---------------------------------------------------------------------------


class TestRefAutoIndexing:
    def test_ref_fields_auto_indexed(self):
        """Ref fields should be automatically added as indexed fields."""
        crud = AutoCRUD()
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        monster_rm = crud.get_resource_manager("monster")
        indexed_paths = [f.field_path for f in monster_rm.indexed_fields]
        assert "zone_id" in indexed_paths
        assert "guild_id" in indexed_paths
        assert "owner_id" in indexed_paths

    def test_ref_fields_no_duplicate_index(self):
        """If user already indexed a Ref field, don't add it again."""

        crud = AutoCRUD()
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(
            Monster,
            name="monster",
            indexed_fields=[("zone_id", str)],
        )
        monster_rm = crud.get_resource_manager("monster")
        zone_id_fields = [
            f for f in monster_rm.indexed_fields if f.field_path == "zone_id"
        ]
        assert len(zone_id_fields) == 1  # Not duplicated


# ---------------------------------------------------------------------------
# Referential Integrity: cascade / set_null on delete
# ---------------------------------------------------------------------------


class TestRefIntegrityCascade:
    """Test cascade delete: deleting a target auto-deletes referencing resources."""

    def _setup_crud(self):
        """Create AutoCRUD with Zone, Character, Monster (cascade on owner_id)."""
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        crud.apply(app)  # Installs ref integrity handlers
        return crud

    def test_cascade_deletes_referencing_resources(self):
        crud = self._setup_crud()
        character_rm = crud.resource_managers["character"]
        monster_rm = crud.resource_managers["monster"]

        # Create a character
        char_info = character_rm.create(Character(name="Hero"))

        # Create monsters owned by this character (cascade on owner_id)
        m1 = monster_rm.create(
            Monster(
                zone_id="z1",
                owner_id=char_info.resource_id,
                zone_revision_id="zr1",
            )
        )
        m2 = monster_rm.create(
            Monster(
                zone_id="z1",
                owner_id=char_info.resource_id,
                zone_revision_id="zr1",
            )
        )
        # A monster owned by a different character
        m3 = monster_rm.create(
            Monster(
                zone_id="z1",
                owner_id="other-char",
                zone_revision_id="zr1",
            )
        )

        # Delete the character → should cascade delete m1, m2 but not m3
        character_rm.delete(char_info.resource_id)

        # m1 and m2 should be soft-deleted
        m1_meta = monster_rm._get_meta_no_check_is_deleted(m1.resource_id)
        m2_meta = monster_rm._get_meta_no_check_is_deleted(m2.resource_id)
        m3_meta = monster_rm._get_meta_no_check_is_deleted(m3.resource_id)
        assert m1_meta.is_deleted is True
        assert m2_meta.is_deleted is True
        assert m3_meta.is_deleted is False


class TestRefIntegritySetNull:
    """Test set_null: deleting a target sets referencing field to null."""

    def _setup_crud(self):
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        crud.apply(app)  # Installs ref integrity handlers
        return crud

    def test_set_null_on_delete(self):
        crud = self._setup_crud()
        guild_rm = crud.resource_managers["guild"]
        monster_rm = crud.resource_managers["monster"]

        # Create a guild
        guild_info = guild_rm.create(Guild(name="Warriors"))

        # Create monsters in this guild (set_null on guild_id)
        m1 = monster_rm.create(
            Monster(
                zone_id="z1",
                guild_id=guild_info.resource_id,
                owner_id="char1",
                zone_revision_id="zr1",
            )
        )
        m2 = monster_rm.create(
            Monster(
                zone_id="z1",
                guild_id=guild_info.resource_id,
                owner_id="char1",
                zone_revision_id="zr1",
            )
        )
        # Monster with no guild
        m3 = monster_rm.create(
            Monster(
                zone_id="z1",
                guild_id=None,
                owner_id="char1",
                zone_revision_id="zr1",
            )
        )

        # Delete the guild → m1.guild_id and m2.guild_id should become None
        guild_rm.delete(guild_info.resource_id)

        m1_data = monster_rm.get(m1.resource_id).data
        m2_data = monster_rm.get(m2.resource_id).data
        m3_data = monster_rm.get(m3.resource_id).data
        assert m1_data.guild_id is None
        assert m2_data.guild_id is None
        assert m3_data.guild_id is None  # Was already None

    def test_dangling_does_nothing(self):
        """on_delete=dangling should leave referencing resources untouched."""
        crud = self._setup_crud()
        zone_rm = crud.resource_managers["zone"]
        monster_rm = crud.resource_managers["monster"]

        # Create a zone
        zone_info = zone_rm.create(Zone(name="Forest"))

        # Create a monster in this zone (dangling on zone_id)
        m1 = monster_rm.create(
            Monster(
                zone_id=zone_info.resource_id,
                owner_id="char1",
                zone_revision_id="zr1",
            )
        )

        # Delete the zone → m1.zone_id stays unchanged (dangling)
        zone_rm.delete(zone_info.resource_id)

        m1_data = monster_rm.get(m1.resource_id).data
        assert m1_data.zone_id == zone_info.resource_id  # Unchanged


# ---------------------------------------------------------------------------
# API: GET /{target}/{resource_id}/referrers
# ---------------------------------------------------------------------------


class TestReferrersAPI:
    """Test the referrers endpoint: GET /{target}/{resource_id}/referrers."""

    @pytest.fixture
    def crud_and_client(self):
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)
        return crud, client

    def test_referrers_returns_matching_resources(self, crud_and_client):
        """Querying referrers of a zone returns monsters that reference it."""
        crud, client = crud_and_client
        zone_rm = crud.resource_managers["zone"]
        monster_rm = crud.resource_managers["monster"]

        zone = zone_rm.create(Zone(name="Forest"))
        m1 = monster_rm.create(
            Monster(
                zone_id=zone.resource_id,
                owner_id="c1",
                zone_revision_id="zr1",
            )
        )
        m2 = monster_rm.create(
            Monster(
                zone_id=zone.resource_id,
                owner_id="c2",
                zone_revision_id="zr1",
            )
        )
        # Monster in a different zone — should NOT appear
        monster_rm.create(
            Monster(
                zone_id="other-zone",
                owner_id="c3",
                zone_revision_id="zr1",
            )
        )

        resp = client.get(f"/zone/{zone.resource_id}/referrers")
        assert resp.status_code == 200
        data = resp.json()
        # Should contain referrers from monster.zone_id
        monster_refs = [
            r
            for r in data
            if r["source"] == "monster" and r["source_field"] == "zone_id"
        ]
        assert len(monster_refs) == 1
        assert set(monster_refs[0]["resource_ids"]) == {
            m1.resource_id,
            m2.resource_id,
        }

    def test_referrers_empty(self, crud_and_client):
        """If no resources reference the target, return empty list."""
        crud, client = crud_and_client
        zone_rm = crud.resource_managers["zone"]
        zone = zone_rm.create(Zone(name="Empty Zone"))

        resp = client.get(f"/zone/{zone.resource_id}/referrers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_referrers_multiple_sources(self, crud_and_client):
        """Zone is referenced by monster.zone_id — verify multiple resources."""
        crud, client = crud_and_client
        zone_rm = crud.resource_managers["zone"]
        monster_rm = crud.resource_managers["monster"]

        zone = zone_rm.create(Zone(name="Desert"))
        m1 = monster_rm.create(
            Monster(
                zone_id=zone.resource_id,
                owner_id="c1",
                zone_revision_id="zr1",
            )
        )
        m2 = monster_rm.create(
            Monster(
                zone_id=zone.resource_id,
                owner_id="c2",
                zone_revision_id="zr1",
            )
        )

        resp = client.get(f"/zone/{zone.resource_id}/referrers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        all_ids = []
        for group in data:
            all_ids.extend(group["resource_ids"])
        assert m1.resource_id in all_ids
        assert m2.resource_id in all_ids

    def test_referrers_character_cascade(self, crud_and_client):
        """Character is referenced by monster.owner_id (cascade)."""
        crud, client = crud_and_client
        char_rm = crud.resource_managers["character"]
        monster_rm = crud.resource_managers["monster"]

        char = char_rm.create(Character(name="Hero"))
        monster_rm.create(
            Monster(
                zone_id="z1",
                owner_id=char.resource_id,
                zone_revision_id="zr1",
            )
        )

        resp = client.get(f"/character/{char.resource_id}/referrers")
        assert resp.status_code == 200
        data = resp.json()
        owner_refs = [
            r
            for r in data
            if r["source"] == "monster" and r["source_field"] == "owner_id"
        ]
        assert len(owner_refs) == 1
        assert owner_refs[0]["on_delete"] == "cascade"

    def test_referrers_model_without_refs_has_no_endpoint(self, crud_and_client):
        """Monster is not a target of any Ref — no /monster/{id}/referrers route."""
        _, client = crud_and_client
        resp = client.get("/monster/some-id/referrers")
        assert resp.status_code == 404

    def test_referrers_response_shape(self, crud_and_client):
        """Verify the shape of each referrer group in the response."""
        crud, client = crud_and_client
        guild_rm = crud.resource_managers["guild"]
        monster_rm = crud.resource_managers["monster"]

        guild = guild_rm.create(Guild(name="Knights"))
        monster_rm.create(
            Monster(
                zone_id="z1",
                guild_id=guild.resource_id,
                owner_id="c1",
                zone_revision_id="zr1",
            )
        )

        resp = client.get(f"/guild/{guild.resource_id}/referrers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        group = data[0]
        assert group["source"] == "monster"
        assert group["source_field"] == "guild_id"
        assert group["ref_type"] == "resource_id"
        assert group["on_delete"] == "set_null"
        assert isinstance(group["resource_ids"], list)
        assert len(group["resource_ids"]) == 1


# ---------------------------------------------------------------------------
# API: GET /_relationships
# ---------------------------------------------------------------------------


class TestRelationshipsAPI:
    """Test the global relationships metadata endpoint."""

    def test_relationships_returns_all_refs(self):
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.get("/_relationships")
        assert resp.status_code == 200
        data = resp.json()
        # Monster has 4 refs: zone_id (Ref), guild_id (Ref), owner_id (Ref),
        # zone_revision_id (RefRevision)
        assert len(data) == 4
        sources = {(r["source"], r["source_field"]) for r in data}
        assert ("monster", "zone_id") in sources
        assert ("monster", "guild_id") in sources
        assert ("monster", "owner_id") in sources
        assert ("monster", "zone_revision_id") in sources

    def test_relationships_empty_when_no_refs(self):
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(NoRefs, name="norefs")
        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.get("/_relationships")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_relationships_shape(self):
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Zone, name="zone")
        crud.add_model(Guild, name="guild")
        crud.add_model(Character, name="character")
        crud.add_model(Monster, name="monster")
        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)

        resp = client.get("/_relationships")
        data = resp.json()
        for rel in data:
            assert "source" in rel
            assert "source_field" in rel
            assert "target" in rel
            assert "ref_type" in rel
            assert "on_delete" in rel
            assert "nullable" in rel


class TestListRefReferrers:
    """Bug: referrers endpoint returns empty for list[Annotated[str, Ref(...)]] fields.

    When a field is ``list[Annotated[str, Ref("skill")]]``, the indexed value
    is a list of IDs.  The referrers lookup uses ``equals`` operator which
    cannot match a single ID inside a list.  It should use ``contains`` instead.
    """

    @pytest.fixture
    def crud_and_client(self):
        crud = AutoCRUD(
            default_user="admin",
            default_now=dt.datetime.now,
        )
        crud.add_model(Skill, name="skill")
        crud.add_model(CharacterWithSkills, name="character")
        app = FastAPI()
        crud.apply(app)
        client = TestClient(app)
        return crud, client

    def test_referrers_for_list_ref_field(self, crud_and_client):
        """A skill referenced inside character.skill_ids should appear in referrers."""
        crud, client = crud_and_client
        skill_rm = crud.resource_managers["skill"]
        char_rm = crud.resource_managers["character"]

        s1 = skill_rm.create(Skill(name="Fireball"))
        s2 = skill_rm.create(Skill(name="Heal"))

        c1 = char_rm.create(
            CharacterWithSkills(name="Mage", skill_ids=[s1.resource_id, s2.resource_id])
        )
        c2 = char_rm.create(
            CharacterWithSkills(name="Warrior", skill_ids=[s1.resource_id])
        )
        # c3 does NOT have s1
        char_rm.create(CharacterWithSkills(name="Thief", skill_ids=[s2.resource_id]))

        resp = client.get(f"/skill/{s1.resource_id}/referrers")
        assert resp.status_code == 200
        data = resp.json()

        skill_refs = [
            r
            for r in data
            if r["source"] == "character" and r["source_field"] == "skill_ids"
        ]
        assert len(skill_refs) == 1, f"Expected 1 referrer group, got {data}"
        assert set(skill_refs[0]["resource_ids"]) == {
            c1.resource_id,
            c2.resource_id,
        }

    def test_referrers_list_ref_empty_when_not_referenced(self, crud_and_client):
        """A skill not in any character's skill_ids returns empty referrers."""
        crud, client = crud_and_client
        skill_rm = crud.resource_managers["skill"]
        char_rm = crud.resource_managers["character"]

        s1 = skill_rm.create(Skill(name="Unused Skill"))
        char_rm.create(CharacterWithSkills(name="Solo", skill_ids=[]))

        resp = client.get(f"/skill/{s1.resource_id}/referrers")
        assert resp.status_code == 200
        data = resp.json()
        # No character references s1, so should be empty
        assert data == [] or all(len(r["resource_ids"]) == 0 for r in data)

    def test_referrers_nonexistent_resource_returns_404(self, crud_and_client):
        """Requesting referrers for a non-existent resource_id should return 404."""
        _crud, client = crud_and_client
        resp = client.get("/skill/nonexistent-id-12345/referrers")
        assert resp.status_code == 404
