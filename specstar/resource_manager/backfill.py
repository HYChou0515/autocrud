"""Batch backfill helpers for Vector / Embedding fields."""

from __future__ import annotations

from dataclasses import dataclass

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
        needs_encode = emb.vector is UNSET or (
            current_encoder_id is not None and emb.encoder_id != current_encoder_id
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


def backfill_set_columns(
    rm: IResourceManager,
    *,
    field_name: str,
) -> BackfillSummary:
    """Repopulate the SetIndex shadow column for ``field_name`` across all
    existing rows — needed for rows written before the column was added.

    Unlike :func:`backfill_vectors`, the shadow column is a pure derivation of
    ``indexed_data`` (no re-encoding), so this delegates to the meta store's
    pushed-down backfill (one SQL ``UPDATE``). A no-op on backends without
    native SetIndex acceleration, which serve ``contains_any`` from the shared
    path and have no shadow column to fill.
    """
    from specstar.types import extract_set_index_field_infos

    names = {i.name for i in extract_set_index_field_infos(rm.resource_type)}
    if field_name not in names:
        raise ValueError(
            f"Field {field_name!r} is not a SetIndex field on "
            f"{rm.resource_type.__name__}"
        )
    summary = BackfillSummary()
    storage = getattr(rm, "storage", None)
    meta_store = getattr(storage, "meta_store", None) if storage is not None else None
    if meta_store is not None and hasattr(meta_store, "backfill_set_column"):
        summary.encoded = meta_store.backfill_set_column(field_name)
    return summary
