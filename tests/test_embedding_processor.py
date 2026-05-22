"""Tests for ``EmbeddingProcessor`` — write-time encoder pipeline for Embedding fields."""

from __future__ import annotations

from typing import Annotated

import pytest
from msgspec import UNSET, Struct

from specstar.resource_manager.embedding_processor import EmbeddingProcessor
from specstar.resource_manager.encoder_registry import EncoderRegistry
from specstar.types import Embedding, Vector


def _stub_encoder_a(text: str) -> list[float]:
    # Deterministic small vector for asserting
    return [float(ord(c)) / 100.0 for c in text[:4].ljust(4, " ")]


def _stub_encoder_b(text: str) -> list[float]:
    # Different output — simulates a different model
    return [1.0, 2.0, 3.0, 4.0]


# EP1: tracer — fresh content gets encoded
@pytest.mark.asyncio
async def test_ep_encode_fresh_content() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="enc_a")]

    reg = EncoderRegistry()
    reg.register("enc_a", _stub_encoder_a)
    processor = EmbeddingProcessor(Doc, reg)

    data = Doc(summary=Embedding(content="hello"))
    result = await processor.process(data)

    assert result.summary.vector == _stub_encoder_a("hello")
    assert result.summary.content == "hello"
    assert result.summary.content_hash is not UNSET
    assert result.summary.encoder_id == "enc_a"


# EP2: user-provided vector preserved (encoder not called)
@pytest.mark.asyncio
async def test_ep_user_vector_preserved() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="enc_a")]

    call_count = 0

    def counting_encoder(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        return [9.9, 9.9, 9.9, 9.9]

    reg = EncoderRegistry()
    reg.register("enc_a", counting_encoder)
    processor = EmbeddingProcessor(Doc, reg)

    user_vec = [0.5, 0.6, 0.7, 0.8]
    data = Doc(summary=Embedding(content="hi", vector=user_vec))
    result = await processor.process(data)

    assert result.summary.vector == user_vec
    assert call_count == 0  # encoder NOT called


# EP3: cache reuse — same content_hash + encoder_id → reuse previous vector
@pytest.mark.asyncio
async def test_ep_cache_reuse_on_match() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="enc_a")]

    call_count = 0

    def counting_encoder(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        return [9.9, 9.9, 9.9, 9.9]

    reg = EncoderRegistry()
    reg.register("enc_a", counting_encoder)
    processor = EmbeddingProcessor(Doc, reg)

    # First process: encoder called once, vector + hash + encoder_id filled
    first = await processor.process(Doc(summary=Embedding(content="same")))
    assert call_count == 1

    # Second process with same content; pass previous as cache source
    second = await processor.process(
        Doc(summary=Embedding(content="same")),
        previous=first,
    )
    assert call_count == 1  # encoder NOT called again
    assert second.summary.vector == first.summary.vector
    assert second.summary.content_hash == first.summary.content_hash
    assert second.summary.encoder_id == first.summary.encoder_id


# EP4: content changed → encoder runs even with previous
@pytest.mark.asyncio
async def test_ep_content_changed_triggers_reencoding() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="enc_a")]

    call_count = 0

    def counting_encoder(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        # Return different vector per text to detect re-encode
        return [float(len(text))] * 4

    reg = EncoderRegistry()
    reg.register("enc_a", counting_encoder)
    processor = EmbeddingProcessor(Doc, reg)

    first = await processor.process(Doc(summary=Embedding(content="short")))
    assert call_count == 1

    # Different content — must re-encode despite passing previous
    second = await processor.process(
        Doc(summary=Embedding(content="much longer content")),
        previous=first,
    )
    assert call_count == 2
    assert second.summary.vector != first.summary.vector
    assert second.summary.content_hash != first.summary.content_hash


# EP5: encoder_id change triggers re-encoding even if content is the same
@pytest.mark.asyncio
async def test_ep_encoder_change_triggers_reencoding() -> None:
    # First model uses enc_a, then re-process with model that uses enc_b
    class DocA(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="enc_a")]

    class DocB(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="enc_b")]

    reg = EncoderRegistry()
    reg.register("enc_a", _stub_encoder_a)
    reg.register("enc_b", _stub_encoder_b)

    proc_a = EmbeddingProcessor(DocA, reg)
    proc_b = EmbeddingProcessor(DocB, reg)

    first = await proc_a.process(DocA(summary=Embedding(content="same")))
    assert first.summary.encoder_id == "enc_a"
    first_vec = first.summary.vector

    # Even though content hash matches, encoder differs → re-encode
    # Cross-type cache reuse via duck-typing: previous has summary.content_hash and encoder_id
    second = await proc_b.process(
        DocB(summary=Embedding(content="same")),
        previous=first,
    )
    assert second.summary.encoder_id == "enc_b"
    assert second.summary.vector == _stub_encoder_b("same")
    assert second.summary.vector != first_vec


# EP6: nullable Embedding with None — encoder not called, value stays None
@pytest.mark.asyncio
async def test_ep_nullable_none_skipped() -> None:
    class Doc(Struct):
        body: Annotated[Embedding | None, Vector(dim=4, encoder="enc_a")] = None

    call_count = 0

    def counting_encoder(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        return [0.0] * 4

    reg = EncoderRegistry()
    reg.register("enc_a", counting_encoder)
    processor = EmbeddingProcessor(Doc, reg)

    result = await processor.process(Doc(body=None))
    assert result.body is None
    assert call_count == 0


# EP7: encoder exception propagates
@pytest.mark.asyncio
async def test_ep_encoder_error_propagates() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="bomb")]

    def bomb_encoder(text: str) -> list[float]:
        raise RuntimeError("api limit")

    reg = EncoderRegistry()
    reg.register("bomb", bomb_encoder)
    processor = EmbeddingProcessor(Doc, reg)

    with pytest.raises(RuntimeError, match="api limit"):
        await processor.process(Doc(summary=Embedding(content="hi")))


# EP8: async encoder awaited correctly
@pytest.mark.asyncio
async def test_ep_async_encoder_awaited() -> None:
    class Doc(Struct):
        summary: Annotated[Embedding, Vector(dim=4, encoder="async_enc")]

    async def async_encoder(text: str) -> list[float]:
        return [42.0, 42.0, 42.0, 42.0]

    reg = EncoderRegistry()
    reg.register("async_enc", async_encoder)
    processor = EmbeddingProcessor(Doc, reg)

    result = await processor.process(Doc(summary=Embedding(content="hi")))
    assert result.summary.vector == [42.0, 42.0, 42.0, 42.0]
