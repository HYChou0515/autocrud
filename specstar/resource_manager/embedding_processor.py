"""Write-time pipeline for Embedding fields.

Traverses a resource struct, identifies ``Embedding``-typed fields, and
fills ``vector`` / ``content_hash`` / ``encoder_id`` by calling the
registered encoder.  Supports cache reuse when a previous revision is
supplied and ``(content_hash, encoder_id)`` match.
"""

from __future__ import annotations

import inspect
from typing import Any

import msgspec
import xxhash
from msgspec import UNSET

from specstar.resource_manager.encoder_registry import (
    EncoderRegistry,
    lookup_encoder,
)
from specstar.types import extract_vector_field_infos


def _content_hash(content: str) -> str:
    return xxhash.xxh3_128_hexdigest(content)


class EmbeddingProcessor:
    """Auto-encodes Embedding fields on write."""

    def __init__(
        self,
        struct_type: type,
        registry: EncoderRegistry,
        *,
        model_overrides: dict | None = None,
    ) -> None:
        self._infos = [
            info
            for info in extract_vector_field_infos(struct_type)
            if info.is_embedding
        ]
        self._registry = registry
        self._model_overrides = model_overrides or {}

    @property
    def reuses_previous(self) -> bool:
        """Whether `previous=` is ever consulted.

        False when the model declares no embedding field — `process_sync` then
        loops over an empty list, so a caller that would have to READ the
        previous revision to supply it can skip that work entirely.
        """
        return bool(self._infos)

    def process_sync(self, data: Any, *, previous: Any | None = None) -> Any:
        """Synchronous variant — raises if any required encoder is async."""
        for info in self._infos:
            emb = getattr(data, info.name, None)
            if emb is None:
                continue
            if emb.vector is not UNSET:
                continue
            encoder = lookup_encoder(
                self._registry, field_info=info, model_overrides=self._model_overrides
            )
            if encoder is None:
                continue
            new_hash = _content_hash(emb.content)
            encoder_id = info.marker.encoder
            if previous is not None:
                prev_emb = getattr(previous, info.name, None)
                if (
                    prev_emb is not None
                    and prev_emb.content_hash == new_hash
                    and prev_emb.encoder_id == encoder_id
                    and prev_emb.vector is not UNSET
                ):
                    new_emb = msgspec.structs.replace(
                        emb,
                        vector=prev_emb.vector,
                        content_hash=new_hash,
                        encoder_id=encoder_id,
                    )
                    data = msgspec.structs.replace(data, **{info.name: new_emb})
                    continue
            vec = encoder(emb.content)
            if inspect.isawaitable(vec):
                raise RuntimeError(
                    f"Encoder for field {info.name!r} is async but write was "
                    f"invoked synchronously. Use the async write path or "
                    f"register a sync encoder."
                )
            new_emb = msgspec.structs.replace(
                emb,
                vector=vec,
                content_hash=new_hash,
                encoder_id=encoder_id,
            )
            data = msgspec.structs.replace(data, **{info.name: new_emb})
        return data

    async def process(self, data: Any, *, previous: Any | None = None) -> Any:
        for info in self._infos:
            emb = getattr(data, info.name, None)
            if emb is None:
                continue
            if emb.vector is not UNSET:
                continue
            encoder = lookup_encoder(
                self._registry, field_info=info, model_overrides=self._model_overrides
            )
            if encoder is None:
                continue
            new_hash = _content_hash(emb.content)
            encoder_id = info.marker.encoder
            # Cache reuse: previous revision had the same content + encoder
            if previous is not None:
                prev_emb = getattr(previous, info.name, None)
                if (
                    prev_emb is not None
                    and prev_emb.content_hash == new_hash
                    and prev_emb.encoder_id == encoder_id
                    and prev_emb.vector is not UNSET
                ):
                    new_emb = msgspec.structs.replace(
                        emb,
                        vector=prev_emb.vector,
                        content_hash=new_hash,
                        encoder_id=encoder_id,
                    )
                    data = msgspec.structs.replace(data, **{info.name: new_emb})
                    continue
            vec = encoder(emb.content)
            if inspect.isawaitable(vec):
                vec = await vec
            new_emb = msgspec.structs.replace(
                emb,
                vector=vec,
                content_hash=new_hash,
                encoder_id=encoder_id,
            )
            data = msgspec.structs.replace(data, **{info.name: new_emb})
        return data
