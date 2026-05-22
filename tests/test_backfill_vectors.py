"""Tests for backfill_vectors — batch re-encoding helper."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from msgspec import UNSET, Struct

from specstar import Embedding, SpecStar, Vector
from specstar.resource_manager.backfill import backfill_vectors


def _stub_encoder(text: str) -> list[float]:
    return [float(len(text)), float(ord(text[0]) if text else 0)]


# BFL1: backfill_vectors encodes rows that were created without an encoder
def test_backfill_vectors_fills_missing() -> None:
    class Doc(Struct):
        title: str
        summary: Annotated[Embedding, Vector(dim=2, encoder="stub")]

    spec = SpecStar(
        default_user="tester",
        default_now=lambda: dt.datetime(2026, 5, 22),
    )
    # Note: encoder NOT registered yet — create() will leave vector UNSET
    spec.add_model(Doc)
    mgr = spec.get_resource_manager(Doc)

    info_a = mgr.create(Doc(title="a", summary=Embedding(content="hello")))
    info_b = mgr.create(Doc(title="b", summary=Embedding(content="world")))

    # Vectors are UNSET because encoder wasn't registered
    assert mgr.get(info_a.resource_id).data.summary.vector is UNSET
    assert mgr.get(info_b.resource_id).data.summary.vector is UNSET

    # Now register the encoder and run backfill
    spec.encoder_registry.register("stub", _stub_encoder)

    summary = backfill_vectors(mgr, field_name="summary")
    assert summary.encoded == 2
    assert summary.skipped == 0
    assert mgr.get(info_a.resource_id).data.summary.vector == _stub_encoder("hello")
    assert mgr.get(info_b.resource_id).data.summary.vector == _stub_encoder("world")

    # Second backfill: nothing to do
    summary = backfill_vectors(mgr, field_name="summary")
    assert summary.encoded == 0
    assert summary.skipped == 2
