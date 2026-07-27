"""Tests for OpenAPI schema name length limits.

PyYAML refuses a "simple key" longer than 1024 characters.  An OpenAPI
component name and a URL path are both mapping keys, so once either crosses
that line the whole document becomes unparseable for every consumer that
routes through PyYAML — which includes ``datamodel-code-generator`` for any
input whose file name does not end in ``.json``.

``msgspec`` walks straight into this: a generic parameterised by a *union*
falls back to module-qualified member names (``Wrap[A]`` → ``Wrap_A_`` but
``Wrap[A | B]`` → ``Wrap___main__.A_____main__.B_``), so the name grows with
the number of union members *times* the length of their module path.

Covers:
- ``_sanitize_schema_names`` shortens over-budget component names and rewrites
  every ``$ref`` and ``discriminator.mapping`` that pointed at them.
- Shortening is deterministic, so a regenerated client does not churn.
- Names within budget are left exactly as they are.
- End-to-end: a union-backed model produces no mapping key over the limit.
"""

from __future__ import annotations

import datetime as dt

import msgspec
import pytest
from fastapi import FastAPI

from specstar.crud.core import _MAX_DERIVED_RESOURCE_NAME, SpecStar
from specstar.crud.route_templates.responses import (
    _MAX_SCHEMA_NAME_LENGTH,
    _sanitize_schema_names,
)
from specstar.schema import Schema

# PyYAML's hard limit on a simple key.
PYYAML_SIMPLE_KEY_LIMIT = 1024


def _long_name(prefix: str = "Wrap", length: int = 1500) -> str:
    """A component name that is over budget but contains no dots."""
    return prefix + "X" * (length - len(prefix))


class TestComponentNameBudget:
    def test_budget_is_below_the_pyyaml_limit(self):
        """The budget must leave room, not sit exactly on the cliff."""
        assert _MAX_SCHEMA_NAME_LENGTH < PYYAML_SIMPLE_KEY_LIMIT

    def test_over_budget_name_is_shortened(self):
        name = _long_name()
        _, components = _sanitize_schema_names([], {name: {"type": "object"}})
        assert name not in components
        (new_name,) = components
        assert len(new_name) <= _MAX_SCHEMA_NAME_LENGTH

    def test_shortened_name_is_much_shorter_than_the_budget(self):
        """A name that had to be replaced should come back readable, not merely legal."""
        _, components = _sanitize_schema_names([], {_long_name(): {"type": "object"}})
        (new_name,) = components
        assert len(new_name) <= 128

    def test_shortened_name_keeps_a_recognisable_prefix(self):
        _, components = _sanitize_schema_names(
            [], {_long_name(prefix="FullResourceResponse"): {"type": "object"}}
        )
        (new_name,) = components
        assert new_name.startswith("FullResourceResponse")

    def test_shortening_is_deterministic(self):
        name = _long_name()
        first = _sanitize_schema_names([], {name: {"type": "object"}})[1]
        second = _sanitize_schema_names([], {name: {"type": "object"}})[1]
        assert list(first) == list(second)

    def test_two_different_long_names_do_not_collide(self):
        """Same prefix, different tails — truncation alone would merge them."""
        a = "Wrap" + "A" * 1500
        b = "Wrap" + "A" * 1499 + "B"
        _, components = _sanitize_schema_names(
            [], {a: {"type": "object"}, b: {"type": "object"}}
        )
        assert len(components) == 2

    def test_name_within_budget_is_untouched(self):
        """Renaming a working name would break the client code that imports it."""
        name = "Wrap" + "X" * 100
        _, components = _sanitize_schema_names([], {name: {"type": "object"}})
        assert list(components) == [name]

    def test_refs_to_a_shortened_name_are_rewritten(self):
        name = _long_name()
        schemas, components = _sanitize_schema_names(
            [{"$ref": f"#/components/schemas/{name}"}],
            {name: {"type": "object"}},
        )
        (new_name,) = components
        assert schemas[0]["$ref"] == f"#/components/schemas/{new_name}"

    def test_nested_refs_are_rewritten(self):
        name = _long_name()
        schemas, components = _sanitize_schema_names(
            [
                {
                    "properties": {
                        "item": {"items": {"$ref": f"#/components/schemas/{name}"}}
                    }
                }
            ],
            {name: {"type": "object"}},
        )
        (new_name,) = components
        ref = schemas[0]["properties"]["item"]["items"]["$ref"]
        assert ref == f"#/components/schemas/{new_name}"

    def test_discriminator_mapping_is_rewritten(self):
        name = _long_name()
        schemas, components = _sanitize_schema_names(
            [
                {
                    "discriminator": {
                        "propertyName": "t",
                        "mapping": {"a": f"#/components/schemas/{name}"},
                    }
                }
            ],
            {name: {"type": "object"}},
        )
        (new_name,) = components
        assert (
            schemas[0]["discriminator"]["mapping"]["a"]
            == f"#/components/schemas/{new_name}"
        )

    def test_dotted_and_over_budget_name_gets_both_treatments(self):
        """The module-qualified msgspec name is the case that actually happens."""
        name = "Wrap_" + "_".join(f"__main__.Member{i:03d}Payload" for i in range(60))
        assert len(name) > _MAX_SCHEMA_NAME_LENGTH
        _, components = _sanitize_schema_names([], {name: {"type": "object"}})
        (new_name,) = components
        assert "." not in new_name
        assert len(new_name) <= _MAX_SCHEMA_NAME_LENGTH


class TestUnionModelEndToEnd:
    """A union-backed model must produce a document PyYAML can actually read."""

    @staticmethod
    def _union_of(n: int):
        members = [
            msgspec.defstruct(
                f"CreateNewCharacter{i:02d}JobPayload",
                [("kind", str, msgspec.field(default=f"k{i}")), ("value", int, 0)],
                tag=True,
            )
            for i in range(n)
        ]
        union = members[0]
        for m in members[1:]:
            union = union | m
        return union

    @pytest.fixture
    def schema(self):
        spec = SpecStar(default_user="tester", default_now=dt.datetime.now)
        spec.add_model(self._union_of(40), name="animal")
        app = FastAPI()
        spec.apply(app)
        spec.openapi(app)
        return app.openapi()

    def test_no_component_name_over_the_pyyaml_limit(self, schema):
        components = schema["components"]["schemas"]
        over = [k for k in components if len(k) > PYYAML_SIMPLE_KEY_LIMIT]
        assert over == []

    def test_no_path_over_the_pyyaml_limit(self, schema):
        over = [p for p in schema["paths"] if len(p) > PYYAML_SIMPLE_KEY_LIMIT]
        assert over == []

    def test_every_ref_still_resolves(self, schema):
        components = schema["components"]["schemas"]
        prefix = "#/components/schemas/"
        missing: list[str] = []

        def walk(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k == "$ref" and isinstance(v, str) and v.startswith(prefix):
                        target = v[len(prefix) :]
                        if target not in components:
                            missing.append(target)
                    else:
                        walk(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk(item)

        walk(schema)
        assert missing == []

    def test_document_parses_as_yaml(self, schema):
        """The regression that started this: PyYAML must be able to read it."""
        import json

        import yaml

        yaml.safe_load(json.dumps(schema))


class TestDerivedResourceNameTooLong:
    """A union's auto-derived name becomes the URL path, so it has a ceiling.

    Shortening it silently would rewrite a live URL, so this is refused up
    front instead — and the refusal has to say exactly what to change.
    """

    @staticmethod
    def _spec() -> SpecStar:
        return SpecStar(default_user="tester", default_now=dt.datetime.now)

    def test_registering_an_oversized_union_is_refused(self):
        union = TestUnionModelEndToEnd._union_of(40)
        with pytest.raises(ValueError):
            self._spec().add_model(union)

    def test_an_explicit_name_is_accepted(self):
        """The fix the message tells you to apply has to actually work."""
        union = TestUnionModelEndToEnd._union_of(40)
        self._spec().add_model(union, name="animal")

    def test_a_schema_wrapped_union_is_refused_too(self):
        """add_model(X) and add_model(Schema(X)) derive the same name."""
        union = TestUnionModelEndToEnd._union_of(40)
        with pytest.raises(ValueError):
            self._spec().add_model(Schema(union, "v1"))

    def test_an_explicit_name_is_accepted_for_a_schema_too(self):
        union = TestUnionModelEndToEnd._union_of(40)
        self._spec().add_model(Schema(union, "v1"), name="animal")

    def test_a_small_union_still_derives_its_name(self):
        """Only names that would break the document are refused."""
        spec = self._spec()
        spec.add_model(TestUnionModelEndToEnd._union_of(2))
        assert spec.resource_managers

    # --- the message itself -------------------------------------------------

    @pytest.fixture
    def message(self) -> str:
        union = TestUnionModelEndToEnd._union_of(40)
        with pytest.raises(ValueError) as excinfo:
            self._spec().add_model(union)
        return str(excinfo.value)

    def test_message_shows_the_exact_call_to_write(self, message):
        assert "spec.add_model(" in message
        assert 'name="' in message

    def test_message_reports_the_measured_length_and_the_limit(self, message):
        assert str(_MAX_DERIVED_RESOURCE_NAME) in message
        assert "1516" in message  # the derived kebab name for 40 members

    def test_message_names_the_union_as_the_cause(self, message):
        assert "union" in message.lower()
        assert "40" in message  # the member count

    def test_message_explains_why_the_limit_exists(self, message):
        assert "1024" in message
        assert "yaml" in message.lower()

    def test_message_quotes_the_start_of_the_derived_name(self, message):
        assert "create-new-character00-job-payload" in message

    def test_message_does_not_dump_the_whole_derived_name(self, message):
        """A 1516-character name in a traceback buries the instruction."""
        assert len(message) < 1000
