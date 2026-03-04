"""Route templates for per-model export/import endpoints.

Two templates are provided:

* :class:`ExportRouteTemplate` — ``GET /{model}/export`` downloads a
  ``.acbak`` archive (optionally filtered with the same params as the
  search endpoint).
* :class:`ImportRouteTemplate` — ``POST /{model}/import`` uploads a
  ``.acbak`` archive and loads it into the datastore.
"""

import io
import textwrap
from typing import TypeVar

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    QueryInputs,
    build_query,
)
from autocrud.types import IResourceManager, OnDuplicate

T = TypeVar("T")


# ======================================================================
# Export
# ======================================================================


class ExportRouteTemplate(BaseRouteTemplate):
    """Per-model export endpoint: ``GET /{model}/export``.

    Supports the same ``QueryInputs`` parameters as the search endpoint
    (``qb``, ``is_deleted``, time ranges …) to filter which resources
    are included in the archive.

    Uses ``order=50`` so the ``/export`` path is registered **before**
    the generic ``/{resource_id}`` read route.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("order", 50)
        super().__init__(**kwargs)

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.get(
            f"/{model_name}/export",
            summary=f"Export {model_name} data",
            tags=[f"{model_name}"],
            description=textwrap.dedent(f"""\
                Export all (or filtered) **{model_name}** resources as a
                streaming ``.acbak`` archive.

                Supports the same query parameters as the search endpoint
                (``qb``, ``is_deleted``, time ranges, etc.) to filter
                which resources are included.
            """),
            responses={
                200: {
                    "content": {"application/octet-stream": {}},
                    "description": "Streaming .acbak archive.",
                }
            },
        )
        async def export_model(
            query_params: QueryInputs = Query(...),
        ) -> StreamingResponse:
            from autocrud.resource_manager.dump_format import (
                DumpStreamWriter,
                EofRecord,
                HeaderRecord,
                ModelEndRecord,
                ModelStartRecord,
            )

            # Build optional filter (None → dump everything)
            query_for_dump = None
            if query_params.qb:
                try:
                    query_for_dump = build_query(query_params)
                except HTTPException:
                    raise
                except Exception as e:
                    raise HTTPException(status_code=400, detail=str(e))

            buf = io.BytesIO()
            writer = DumpStreamWriter(buf)
            writer.write(HeaderRecord())
            writer.write(ModelStartRecord(model_name=model_name))
            for record in resource_manager.dump(query=query_for_dump):
                writer.write(record)
            writer.write(ModelEndRecord(model_name=model_name))
            writer.write(EofRecord())

            buf.seek(0)
            filename = f"{model_name}.acbak"
            return StreamingResponse(
                buf,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{filename}"',
                },
            )


# ======================================================================
# Import
# ======================================================================


class ImportRouteTemplate(BaseRouteTemplate):
    """Per-model import endpoint: ``POST /{model}/import``.

    Accepts a ``.acbak`` archive upload and loads the records into the
    resource manager.  The archive **must** contain a model section whose
    name matches *model_name*; other model sections are skipped.

    Uses ``order=50`` so the ``/import`` path is registered before
    the generic ``/{resource_id}`` read route.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("order", 50)
        super().__init__(**kwargs)

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        @router.post(
            f"/{model_name}/import",
            summary=f"Import {model_name} data",
            tags=[f"{model_name}"],
            description=textwrap.dedent(f"""\
                Import **{model_name}** resources from a ``.acbak`` archive.

                The archive must contain a **{model_name}** model section.
                Use ``on_duplicate`` to control behaviour when a resource ID
                already exists.
            """),
        )
        async def import_model(
            file: UploadFile = File(..., description=".acbak archive file"),
            on_duplicate: str = Query(
                "overwrite",
                description="Strategy: overwrite | skip | raise_error",
            ),
        ) -> dict:
            from autocrud.resource_manager.dump_format import (
                BlobRecord,
                DumpStreamReader,
                EofRecord,
                HeaderRecord,
                MetaRecord,
                ModelEndRecord,
                ModelStartRecord,
                RevisionRecord,
            )

            # --- validate on_duplicate --------------------------------
            try:
                strategy = OnDuplicate(on_duplicate)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid on_duplicate: {on_duplicate}. "
                        "Must be one of: overwrite, skip, raise_error"
                    ),
                )

            # --- read & validate archive ------------------------------
            data = await file.read()
            reader = DumpStreamReader(io.BytesIO(data))

            try:
                first = next(reader)
            except StopIteration:
                raise HTTPException(status_code=400, detail="Empty archive.")
            if not isinstance(first, HeaderRecord):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Invalid archive: expected header, got {type(first).__name__}."
                    ),
                )
            if first.version != 2:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported archive version {first.version}.",
                )

            # --- iterate records & load -------------------------------
            loaded = 0
            skipped = 0
            total = 0
            skipped_ids: set[str] = set()
            in_target_section = False

            for record in reader:
                if isinstance(record, ModelStartRecord):
                    in_target_section = record.model_name == model_name

                elif isinstance(record, ModelEndRecord):
                    in_target_section = False

                elif isinstance(record, MetaRecord):
                    if not in_target_section:
                        continue
                    total += 1
                    try:
                        ok = resource_manager.load_record(record, strategy)
                    except Exception as e:
                        raise HTTPException(status_code=409, detail=str(e))
                    if ok:
                        loaded += 1
                    else:
                        skipped += 1
                        # Decode meta to track skipped resource ids so we
                        # can skip their revisions too.
                        meta = resource_manager.meta_serializer.decode(record.data)
                        skipped_ids.add(meta.resource_id)

                elif isinstance(record, RevisionRecord):
                    if not in_target_section:
                        continue
                    raw = resource_manager.resource_serializer.decode(record.data)
                    if raw.info.resource_id in skipped_ids:
                        continue
                    resource_manager.load_record(record, strategy)

                elif isinstance(record, BlobRecord):
                    if not in_target_section:
                        continue
                    resource_manager.load_record(record, strategy)

                elif isinstance(record, EofRecord):
                    break

            return {"loaded": loaded, "skipped": skipped, "total": total}
