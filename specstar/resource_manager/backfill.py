"""Batch backfill helpers for Vector / Embedding fields."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from msgspec import UNSET

from specstar.query_types import ResourceMetaSearchQuery
from specstar.types import IResourceManager, extract_vector_field_infos


@dataclass(slots=True)
class BackfillSummary:
    """Result of a backfill run."""

    encoded: int = 0
    skipped: int = 0


def backfill_vectors(
    rm: IResourceManager,
    *,
    field_name: str,
) -> BackfillSummary:
    """Re-encode ``field_name`` for every resource where the stored vector
    is missing or stale relative to the field's configured encoder.

    Only supports Embedding fields (the source ``content`` is needed to
    re-encode).
    """
    summary = BackfillSummary()
    infos = {
        i.name: i
        for i in extract_vector_field_infos(rm.resource_type)
        if i.is_embedding
    }
    info = infos.get(field_name)
    if info is None:
        raise ValueError(
            f"Field {field_name!r} is not an Embedding-typed Vector field "
            f"on {rm.resource_type.__name__}"
        )
    current_encoder_id = info.marker.encoder

    for meta in rm.search_resources(ResourceMetaSearchQuery()):
        try:
            data = rm.get(meta.resource_id).data
        except Exception:
            summary.skipped += 1
            continue
        emb = getattr(data, field_name, None)
        if emb is None:
            summary.skipped += 1
            continue
        needs_encode = (
            emb.vector is UNSET
            or (
                current_encoder_id is not None
                and emb.encoder_id != current_encoder_id
            )
        )
        if not needs_encode:
            summary.skipped += 1
            continue
        # Reset vector so the processor re-encodes on update
        import msgspec

        fresh_emb = msgspec.structs.replace(emb, vector=UNSET)
        fresh_data = msgspec.structs.replace(data, **{field_name: fresh_emb})
        rm.update(meta.resource_id, fresh_data)
        summary.encoded += 1
    return summary
