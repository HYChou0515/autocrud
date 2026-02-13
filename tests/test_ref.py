"""Tests for Ref / RefRevision resource reference system."""

import datetime as dt
from typing import Annotated

import pytest
from fastapi import FastAPI
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.types import (
    OnDelete,
    Ref,
    RefRevision,
    ResourceIsDeletedError,
    extract_refs,
)

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Zone(Struct):
    name: str


class Character(Struct):
    name: str


class Guild(Struct):
    name: str


class Monster(Struct):
    name: str
    zone_id: Annotated[str, Ref("zone")]
    zone_revision_id: Annotated[str, RefRevision("zone")]
    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.cascade)]
    guild_id: Annotated[str | None, Ref("guild", on_delete=OnDelete.set_null)] = None
    parent_id: Annotated[str | None, Ref("monster")] = None


class Item(Struct):
    name: str
    owner_id: Annotated[str, Ref("character", on_delete=OnDelete.cascade)]


# ---------------------------------------------------------------------------
# Unit Tests: Ref / RefRevision types
# ---------------------------------------------------------------------------


class TestRefTypes:
    def test_ref_repr(self):
        r = Ref("zone")
        assert repr(r) == "Ref('zone', on_delete=<OnDelete.dangling: 'dangling'>)"

    def test_ref_equality(self):
        assert Ref("zone") == Ref("zone")
        assert Ref("zone") != Ref("guild")
        assert Ref("zone", on_delete=OnDelete.cascade) != Ref("zone")

    def test_ref_hashable(self):
        s = {Ref("zone"), Ref("zone"), Ref("guild")}
        assert len(s) == 2

    def test_ref_revision_repr(self):
        r = RefRevision("zone")
        assert repr(r) == "RefRevision('zone')"

    def test_ref_revision_equality(self):
        assert RefRevision("zone") == RefRevision("zone")
        assert RefRevision("zone") != RefRevision("guild")

    def test_on_delete_enum_values(self):
        assert OnDelete.dangling == "dangling"
        assert OnDelete.set_null == "set_null"
        assert OnDelete.cascade == "cascade"


# ---------------------------------------------------------------------------
# Unit Tests: extract_refs
# ---------------------------------------------------------------------------


class TestExtractRefs:
    def test_extract_all_refs(self):
        refs = extract_refs(Monster, "monster")
        assert len(refs) == 5

    def test_extract_required_ref(self):
        refs = extract_refs(Monster, "monster")
        zone_ref = next(r for r in refs if r.source_field == "zone_id")
        assert zone_ref.target == "zone"
        assert zone_ref.ref_type == "resource_id"
        assert zone_ref.on_delete == OnDelete.dangling
        assert zone_ref.nullable is False

    def test_extract_ref_revision(self):
        refs = extract_refs(Monster, "monster")
        rev_ref = next(r for r in refs if r.source_field == "zone_revision_id")
        assert rev_ref.target == "zone"
        assert rev_ref.ref_type == "revision_id"
        assert rev_ref.on_delete == OnDelete.dangling

    def test_extract_cascade_ref(self):
        refs = extract_refs(Monster, "monster")
        owner_ref = next(r for r in refs if r.source_field == "owner_id")
        assert owner_ref.target == "character"
        assert owner_ref.on_delete == OnDelete.cascade
        assert owner_ref.nullable is False

    def test_extract_nullable_set_null_ref(self):
        refs = extract_refs(Monster, "monster")
        guild_ref = next(r for r in refs if r.source_field == "guild_id")
        assert guild_ref.target == "guild"
        assert guild_ref.on_delete == OnDelete.set_null
        assert guild_ref.nullable is True

    def test_extract_self_ref(self):
        refs = extract_refs(Monster, "monster")
        parent_ref = next(r for r in refs if r.source_field == "parent_id")
        assert parent_ref.target == "monster"
        assert parent_ref.on_delete == OnDelete.dangling
        assert parent_ref.nullable is True

    def test_no_refs(self):
        refs = extract_refs(Zone, "zone")
        assert refs == []

    def test_source_name_is_set(self):
        refs = extract_refs(Monster, "my-monster")
        assert all(r.source == "my-monster" for r in refs)


# ---------------------------------------------------------------------------
# Unit Tests: add_model validation
# ---------------------------------------------------------------------------


class TestAddModelValidation:
    def test_set_null_on_non_optional_raises(self):
        class Bad(Struct):
            ref_id: Annotated[str, Ref("zone", on_delete=OnDelete.set_null)]

        crud = AutoCRUD()
        with pytest.raises(ValueError, match="set_null.*not Optional"):
            crud.add_model(Bad)

    def test_relationships_collected(self):
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        assert len(crud.relationships) == 5
        targets = {r.target for r in crud.relationships}
        assert targets == {"zone", "character", "guild", "monster"}

    def test_dangling_ref_warning(self, caplog):
        """Ref to unregistered resource logs a warning at apply() time."""
        crud = AutoCRUD()
        crud.add_model(Monster)
        # zone, character, guild are NOT registered
        crud.apply(FastAPI())
        assert "not registered" in caplog.text


# ---------------------------------------------------------------------------
# Integration Tests: OpenAPI x-ref-* metadata
# ---------------------------------------------------------------------------


class TestOpenAPIRefMetadata:
    @pytest.fixture()
    def app_with_refs(self):
        app = FastAPI(title="Test")
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        crud.apply(app)
        crud.openapi(app)
        return app

    def test_required_ref_has_x_ref(self, app_with_refs):
        props = app_with_refs.openapi_schema["components"]["schemas"]["Monster"][
            "properties"
        ]
        assert props["zone_id"]["x-ref-resource"] == "zone"
        assert props["zone_id"]["x-ref-type"] == "resource_id"
        assert props["zone_id"]["x-ref-on-delete"] == "dangling"

    def test_revision_ref_has_x_ref(self, app_with_refs):
        props = app_with_refs.openapi_schema["components"]["schemas"]["Monster"][
            "properties"
        ]
        assert props["zone_revision_id"]["x-ref-resource"] == "zone"
        assert props["zone_revision_id"]["x-ref-type"] == "revision_id"
        # revision refs should not have on_delete
        assert "x-ref-on-delete" not in props["zone_revision_id"]

    def test_cascade_ref_has_x_ref(self, app_with_refs):
        props = app_with_refs.openapi_schema["components"]["schemas"]["Monster"][
            "properties"
        ]
        assert props["owner_id"]["x-ref-on-delete"] == "cascade"

    def test_nullable_ref_has_x_ref_at_property_level(self, app_with_refs):
        props = app_with_refs.openapi_schema["components"]["schemas"]["Monster"][
            "properties"
        ]
        guild = props["guild_id"]
        # x-ref-* should be at the property level, alongside anyOf
        assert guild["x-ref-resource"] == "guild"
        assert guild["x-ref-on-delete"] == "set_null"
        assert "anyOf" in guild  # still has nullable union

    def test_top_level_relationships(self, app_with_refs):
        rels = app_with_refs.openapi_schema.get("x-autocrud-relationships")
        assert rels is not None
        assert len(rels) == 5
        cascade_rels = [r for r in rels if r["onDelete"] == "cascade"]
        assert len(cascade_rels) == 1
        assert cascade_rels[0]["source"] == "monster"
        assert cascade_rels[0]["target"] == "character"

    def test_no_refs_no_x_autocrud_relationships(self):
        app = FastAPI(title="Test")
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.apply(app)
        crud.openapi(app)
        assert "x-autocrud-relationships" not in app.openapi_schema


# ---------------------------------------------------------------------------
# Integration Tests: on_delete cascade
# ---------------------------------------------------------------------------


class TestOnDeleteCascade:
    @pytest.fixture()
    def crud(self):
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        crud.add_model(Item)
        crud.apply(FastAPI())
        return crud

    def _create(self, rm, data):
        with rm.meta_provide("test-user", dt.datetime.now()):
            return rm.create(data)

    def _delete(self, rm, resource_id):
        with rm.meta_provide("test-user", dt.datetime.now()):
            return rm.delete(resource_id)

    def test_cascade_deletes_referencing_resources(self, crud):
        zm, cm, mm = (
            crud.resource_managers["zone"],
            crud.resource_managers["character"],
            crud.resource_managers["monster"],
        )
        z = self._create(zm, Zone(name="Forest"))
        c = self._create(cm, Character(name="Hero"))
        m1 = self._create(
            mm,
            Monster(
                name="Goblin",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
            ),
        )
        m2 = self._create(
            mm,
            Monster(
                name="Orc",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
            ),
        )

        # Delete character → monsters should be cascade deleted
        self._delete(cm, c.resource_id)

        with pytest.raises(ResourceIsDeletedError):
            mm.get_meta(m1.resource_id)
        with pytest.raises(ResourceIsDeletedError):
            mm.get_meta(m2.resource_id)

    def test_cascade_across_multiple_resources(self, crud):
        """Character deletion cascades to both Monster and Item."""
        cm = crud.resource_managers["character"]
        zm = crud.resource_managers["zone"]
        mm = crud.resource_managers["monster"]
        im = crud.resource_managers["item"]

        z = self._create(zm, Zone(name="Cave"))
        c = self._create(cm, Character(name="Warrior"))
        m = self._create(
            mm,
            Monster(
                name="Bat",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
            ),
        )
        i = self._create(im, Item(name="Sword", owner_id=c.resource_id))

        self._delete(cm, c.resource_id)

        with pytest.raises(ResourceIsDeletedError):
            mm.get_meta(m.resource_id)
        with pytest.raises(ResourceIsDeletedError):
            im.get_meta(i.resource_id)

    def test_cascade_does_not_affect_unrelated(self, crud):
        """Deleting one character doesn't affect monsters owned by another."""
        cm = crud.resource_managers["character"]
        zm = crud.resource_managers["zone"]
        mm = crud.resource_managers["monster"]

        z = self._create(zm, Zone(name="Plains"))
        c1 = self._create(cm, Character(name="A"))
        c2 = self._create(cm, Character(name="B"))
        m1 = self._create(
            mm,
            Monster(
                name="Goblin",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c1.resource_id,
            ),
        )
        m2 = self._create(
            mm,
            Monster(
                name="Orc",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c2.resource_id,
            ),
        )

        self._delete(cm, c1.resource_id)

        # m1 cascade deleted, m2 still alive
        with pytest.raises(ResourceIsDeletedError):
            mm.get_meta(m1.resource_id)
        meta2 = mm.get_meta(m2.resource_id)
        assert meta2.is_deleted is False


# ---------------------------------------------------------------------------
# Integration Tests: on_delete set_null
# ---------------------------------------------------------------------------


class TestOnDeleteSetNull:
    @pytest.fixture()
    def crud(self):
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        crud.apply(FastAPI())
        return crud

    def _create(self, rm, data):
        with rm.meta_provide("test-user", dt.datetime.now()):
            return rm.create(data)

    def _delete(self, rm, resource_id):
        with rm.meta_provide("test-user", dt.datetime.now()):
            return rm.delete(resource_id)

    def test_set_null_clears_ref_field(self, crud):
        zm, cm, gm, mm = (
            crud.resource_managers["zone"],
            crud.resource_managers["character"],
            crud.resource_managers["guild"],
            crud.resource_managers["monster"],
        )
        z = self._create(zm, Zone(name="Forest"))
        c = self._create(cm, Character(name="Hero"))
        g = self._create(gm, Guild(name="Warriors"))
        m = self._create(
            mm,
            Monster(
                name="Goblin",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
                guild_id=g.resource_id,
            ),
        )

        # Delete guild → monster's guild_id should become None
        self._delete(gm, g.resource_id)

        data = mm.get(m.resource_id).data
        assert data.guild_id is None
        # Monster itself should NOT be deleted
        assert mm.get_meta(m.resource_id).is_deleted is False

    def test_set_null_multiple_referencing(self, crud):
        zm, cm, gm, mm = (
            crud.resource_managers["zone"],
            crud.resource_managers["character"],
            crud.resource_managers["guild"],
            crud.resource_managers["monster"],
        )
        z = self._create(zm, Zone(name="Desert"))
        c = self._create(cm, Character(name="Mage"))
        g = self._create(gm, Guild(name="Wizards"))
        m1 = self._create(
            mm,
            Monster(
                name="Slime",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
                guild_id=g.resource_id,
            ),
        )
        m2 = self._create(
            mm,
            Monster(
                name="Bat",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
                guild_id=g.resource_id,
            ),
        )

        self._delete(gm, g.resource_id)

        assert mm.get(m1.resource_id).data.guild_id is None
        assert mm.get(m2.resource_id).data.guild_id is None

    def test_set_null_ignores_already_null(self, crud):
        """Monsters with guild_id=None should not be affected."""
        zm, cm, gm, mm = (
            crud.resource_managers["zone"],
            crud.resource_managers["character"],
            crud.resource_managers["guild"],
            crud.resource_managers["monster"],
        )
        z = self._create(zm, Zone(name="Valley"))
        c = self._create(cm, Character(name="Rogue"))
        g = self._create(gm, Guild(name="Thieves"))
        # Monster without guild
        m = self._create(
            mm,
            Monster(
                name="Wolf",
                zone_id=z.resource_id,
                zone_revision_id=z.revision_id,
                owner_id=c.resource_id,
            ),
        )

        # Delete guild should not touch this monster
        self._delete(gm, g.resource_id)

        data = mm.get(m.resource_id).data
        assert data.guild_id is None
        assert mm.get_meta(m.resource_id).is_deleted is False


# ---------------------------------------------------------------------------
# Integration Tests: dangling (no action)
# ---------------------------------------------------------------------------


class TestOnDeleteDangling:
    def test_dangling_ref_no_action(self):
        """Deleting zone should NOT cascade or set_null on monster.zone_id."""
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        crud.apply(FastAPI())

        zm = crud.resource_managers["zone"]
        cm = crud.resource_managers["character"]
        mm = crud.resource_managers["monster"]

        now = dt.datetime.now()
        with zm.meta_provide("sys", now):
            z = zm.create(Zone(name="Forest"))
        with cm.meta_provide("sys", now):
            c = cm.create(Character(name="Hero"))
        with mm.meta_provide("sys", now):
            m = mm.create(
                Monster(
                    name="Goblin",
                    zone_id=z.resource_id,
                    zone_revision_id=z.revision_id,
                    owner_id=c.resource_id,
                )
            )

        with zm.meta_provide("sys", now):
            zm.delete(z.resource_id)

        # Monster should still be alive with the old zone_id (dangling)
        data = mm.get(m.resource_id).data
        assert data.zone_id == z.resource_id
        assert mm.get_meta(m.resource_id).is_deleted is False


# ---------------------------------------------------------------------------
# Integration Tests: auto-indexing
# ---------------------------------------------------------------------------


class TestAutoIndexing:
    def test_ref_field_auto_indexed_for_cascade(self):
        """Fields with on_delete=cascade should be auto-indexed."""
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        crud.apply(FastAPI())

        mm = crud.resource_managers["monster"]
        indexed_paths = [f.field_path for f in mm.indexed_fields]
        assert "owner_id" in indexed_paths  # cascade
        assert "guild_id" in indexed_paths  # set_null

    def test_ref_field_not_indexed_for_dangling(self):
        """Fields with on_delete=dangling should NOT be auto-indexed."""
        crud = AutoCRUD()
        crud.add_model(Zone)
        crud.add_model(Character)
        crud.add_model(Guild)
        crud.add_model(Monster)
        crud.apply(FastAPI())

        mm = crud.resource_managers["monster"]
        indexed_paths = [f.field_path for f in mm.indexed_fields]
        # zone_id is dangling → not auto-indexed
        assert "zone_id" not in indexed_paths
