"""Tests for the ``specstar backfill-vectors`` CLI command."""

from __future__ import annotations

import datetime as dt
import io
import sys
from typing import Annotated

import pytest
from msgspec import UNSET, Struct

from specstar import Embedding, SpecStar, Vector
from specstar.cli._backfill import backfill_vectors_cmd


def _stub_encoder(text: str) -> list[float]:
    return [float(len(text)), float(ord(text[0]) if text else 0)]


# Module-level for CLI loader to find by string reference
class _Doc(Struct):
    title: str
    summary: Annotated[Embedding, Vector(dim=2, encoder="stub")]


def _make_spec_with_rows():
    s = SpecStar(
        default_user="t",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    s.add_model(_Doc, name="doc")
    mgr = s.get_resource_manager(_Doc)
    mgr.create(_Doc(title="a", summary=Embedding(content="hello")))
    mgr.create(_Doc(title="b", summary=Embedding(content="world")))
    return s


# Module-level binding for "spec_module:spec_attr" CLI argument
_spec_for_cli = None


def _build_cli_spec() -> SpecStar:
    global _spec_for_cli
    _spec_for_cli = _make_spec_with_rows()
    # register encoder after creation so vectors are initially UNSET
    _spec_for_cli.encoder_registry.register("stub", _stub_encoder)
    return _spec_for_cli


# BFLCLI1: CLI loads spec + runs backfill + prints summary
def test_bfl_cli_runs_backfill_and_prints_summary(monkeypatch) -> None:
    spec = _build_cli_spec()

    # Stash the spec into a module reachable by 'module:attr'
    import types

    fake_mod = types.ModuleType("fake_app")
    fake_mod.spec = spec  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fake_app", fake_mod)

    # Confirm initial state: vectors UNSET
    mgr = spec.get_resource_manager(_Doc)
    metas = mgr.search_resources(
        __import__(
            "specstar.query_types", fromlist=["ResourceMetaSearchQuery"]
        ).ResourceMetaSearchQuery()
    )
    rids = [m.resource_id for m in metas]
    for rid in rids:
        assert mgr.get(rid).data.summary.vector is UNSET

    import argparse

    args = argparse.Namespace(
        spec="fake_app:spec",
        model="doc",
        field="summary",
    )
    out = io.StringIO()
    err = io.StringIO()
    exit_code = backfill_vectors_cmd(args, stream=out, error_stream=err)
    assert exit_code == 0
    assert "encoded=2" in out.getvalue()

    # Vectors now populated
    for rid in rids:
        assert mgr.get(rid).data.summary.vector == _stub_encoder(
            mgr.get(rid).data.summary.content
        )
