"""Slice 4: loud-but-suppressible startup warnings for permissive defaults.

At ``apply()`` SpecStar warns (once, via :class:`SpecStarWarning`) when the
default path leaves a known footgun open: unknown-field dropping is off, or no
query limit is configured. Explicit settings silence the respective warning.
"""

import msgspec
import pytest
from fastapi import FastAPI

from specstar import Schema, SpecStar
from specstar.errors import SpecStarWarning


class Item(msgspec.Struct):
    name: str


def test_warns_when_forbid_unknown_fields_off(monkeypatch):
    monkeypatch.setenv("SPECSTAR_DEFAULT_QUERY_LIMIT", "1000")  # silence the other one
    sp = SpecStar()
    sp.configure()
    sp.add_model(Schema(Item, "v1"))
    with pytest.warns(SpecStarWarning, match="forbid_unknown_fields"):
        sp.apply(FastAPI())


def test_warns_when_no_query_limit_configured(monkeypatch):
    monkeypatch.delenv("SPECSTAR_DEFAULT_QUERY_LIMIT", raising=False)
    sp = SpecStar()
    sp.configure(forbid_unknown_fields=True)  # silence the other one
    sp.add_model(Schema(Item, "v1"))
    with pytest.warns(SpecStarWarning, match="SPECSTAR_DEFAULT_QUERY_LIMIT"):
        sp.apply(FastAPI())


def test_warns_when_validate_refs_off(monkeypatch):
    monkeypatch.setenv("SPECSTAR_DEFAULT_QUERY_LIMIT", "1000")  # silence
    sp = SpecStar(forbid_unknown_fields=True, default_get_returns="only-data")  # silence
    sp.add_model(Schema(Item, "v1"))
    with pytest.warns(SpecStarWarning, match="validate_refs"):
        sp.apply(FastAPI())


def test_hardened_config_emits_no_warning(monkeypatch):
    import warnings as w

    monkeypatch.setenv("SPECSTAR_DEFAULT_QUERY_LIMIT", "1000")
    sp = SpecStar(
        forbid_unknown_fields=True,
        validate_refs=True,
        default_get_returns="data,revision_info,meta",  # explicit shape: silences advisory
    )
    sp.add_model(Schema(Item, "v1"))
    with w.catch_warnings(record=True) as rec:
        w.simplefilter("always")
        sp.apply(FastAPI())
    assert not [r for r in rec if issubclass(r.category, SpecStarWarning)]
