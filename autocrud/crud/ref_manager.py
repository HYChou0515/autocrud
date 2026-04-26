from __future__ import annotations

from collections import defaultdict

from autocrud.events import (
    EventContext,
    HasResourceId,
    IEventHandler,
)
from autocrud.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from autocrud.types import (
    IResourceManager,
    OnDelete,
    ResourceAction,
    _RefInfo,
)


class _RefIntegrityHandler(IEventHandler):
    """Internal event handler that enforces referential integrity on delete.

    When a *target* resource is deleted, this handler iterates over all
    ``_RefInfo`` entries that reference the target and applies the configured
    ``on_delete`` action:

    * ``cascade``  — soft-delete each referencing resource.
    * ``set_null`` — set the referencing field to ``None`` via update.
    * ``dangling`` — (not handled here; no action needed).
    """

    def __init__(
        self,
        refs: list[_RefInfo],
        resource_managers: dict[str, IResourceManager],
    ):
        self._refs = refs
        self._resource_managers = resource_managers

    def is_supported(self, context: EventContext) -> bool:
        return isinstance(context, HasResourceId) and (
            context.phase == "on_success" and context.action is ResourceAction.delete
        )

    def handle_event(self, context: EventContext) -> None:
        if not isinstance(context, HasResourceId):
            return
        deleted_resource_id: str = context.resource_id
        for ref_info in self._refs:
            source_rm = self._resource_managers.get(ref_info.source)
            if source_rm is None:
                continue

            matching = source_rm.search_resources(
                ResourceMetaSearchQuery(
                    is_deleted=False,
                    conditions=[
                        DataSearchCondition(
                            field_path=ref_info.source_field,
                            operator=DataSearchOperator.equals,
                            value=deleted_resource_id,
                        )
                    ],
                    limit=10_000,
                )
            )

            for meta in matching:
                if ref_info.on_delete == OnDelete.cascade:
                    source_rm.delete(meta.resource_id)
                elif ref_info.on_delete == OnDelete.set_null:
                    from jsonpatch import JsonPatch

                    patch = JsonPatch(
                        [
                            {
                                "op": "replace",
                                "path": f"/{ref_info.source_field}",
                                "value": None,
                            }
                        ]
                    )
                    source_rm.patch(meta.resource_id, patch)


def install_ref_integrity_handlers(
    relationships: list[_RefInfo],
    resource_managers: dict[str, IResourceManager],
) -> None:
    """Install _RefIntegrityHandler on each target ResourceManager.

    For each registered resource that is a *target* of a ``Ref`` with
    ``on_delete`` of ``cascade`` or ``set_null``, registers a
    ``_RefIntegrityHandler`` on the target's ``ResourceManager`` so that
    when the target is deleted the referencing resources are automatically
    updated.
    """
    registered = set(resource_managers.keys())
    target_refs: dict[str, list[_RefInfo]] = defaultdict(list)
    for ref_info in relationships:
        if (
            ref_info.on_delete != OnDelete.dangling
            and ref_info.target in registered
            and ref_info.source in registered
        ):
            target_refs[ref_info.target].append(ref_info)

    for target_name, refs in target_refs.items():
        handler = _RefIntegrityHandler(
            refs=refs,
            resource_managers=resource_managers,
        )
        target_rm = resource_managers[target_name]
        target_rm.event_handlers.append(handler)
