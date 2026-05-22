from __future__ import annotations

from collections import defaultdict

from specstar.events import (
    ContextFunc,
    EventContext,
    do,
)
from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from specstar.types import (
    IResourceManager,
    OnDelete,
    ResourceAction,
    ResourceConflictError,
    _RefInfo,
)


def _make_ref_integrity_func(
    refs: list[_RefInfo],
    resource_managers: dict[str, IResourceManager],
) -> ContextFunc:
    """Build the ``on_success + delete`` callback that enforces referential integrity.

    When a *target* resource is deleted, the returned callback iterates over
    all ``_RefInfo`` entries that reference the target and applies the
    configured ``on_delete`` action:

    * ``cascade``  — soft-delete each referencing resource.
    * ``set_null`` — set the referencing field to ``None`` via update.
    * ``dangling`` — (not handled here; no action needed).

    ``restrict`` is enforced *before* the delete fires via a separate
    ``before_delete`` handler (see :func:`_make_restrict_check_func`), so
    that the delete itself never happens when references exist.
    """

    def _handle(context: EventContext) -> None:
        deleted_resource_id: str = context.resource_id  # ty:ignore[unresolved-attribute]
        for ref_info in refs:
            if ref_info.on_delete == OnDelete.restrict:
                # Handled by the before-delete guard.
                continue
            source_rm = resource_managers.get(ref_info.source)
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

    return _handle


def _make_restrict_check_func(
    refs: list[_RefInfo],
    resource_managers: dict[str, IResourceManager],
) -> ContextFunc:
    """Build the ``before + delete`` callback that enforces ``OnDelete.restrict``.

    Raises :class:`ResourceConflictError` (HTTP 409) when any
    ``OnDelete.restrict`` reference still points at the resource that is
    about to be deleted, naming the source resource(s) that block the
    delete.
    """

    def _check(context: EventContext) -> None:
        target_resource_id: str = context.resource_id  # ty:ignore[unresolved-attribute]
        blockers: list[tuple[str, str, str]] = []
        for ref_info in refs:
            if ref_info.on_delete != OnDelete.restrict:
                continue
            source_rm = resource_managers.get(ref_info.source)
            if source_rm is None:
                continue
            matching = source_rm.search_resources(
                ResourceMetaSearchQuery(
                    is_deleted=False,
                    conditions=[
                        DataSearchCondition(
                            field_path=ref_info.source_field,
                            operator=DataSearchOperator.equals,
                            value=target_resource_id,
                        )
                    ],
                    limit=10,
                )
            )
            for meta in matching:
                blockers.append(
                    (ref_info.source, ref_info.source_field, meta.resource_id)
                )
        if blockers:
            blocker_list = ", ".join(
                f"{src}.{field}=<-{rid}" for src, field, rid in blockers[:5]
            )
            more = "" if len(blockers) <= 5 else f" (+{len(blockers) - 5} more)"
            raise ResourceConflictError(
                f"Cannot delete '{target_resource_id}': still referenced by "
                f"{blocker_list}{more} (on_delete=RESTRICT)."
            )

    return _check


def install_ref_integrity_handlers(
    relationships: list[_RefInfo],
    resource_managers: dict[str, IResourceManager],
) -> None:
    """Install referential integrity event handlers on each target ResourceManager.

    For each registered resource that is a *target* of a ``Ref`` with
    ``on_delete`` of ``cascade`` or ``set_null``, registers an
    ``on_success + delete`` event handler (built via the ``do(...)`` Builder
    Helper) on the target's ``ResourceManager`` so that when the target is
    deleted the referencing resources are automatically updated.
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
        target_rm = resource_managers[target_name]
        target_rm.event_handlers.extend(  # ty:ignore[unresolved-attribute]
            do(_make_ref_integrity_func(refs, resource_managers)).on_success(
                ResourceAction.delete
            )
        )
        # ``OnDelete.restrict`` must run *before* the delete so we can block
        # it. ``cascade`` / ``set_null`` still run on_success above.
        if any(r.on_delete == OnDelete.restrict for r in refs):
            target_rm.event_handlers.extend(  # ty:ignore[unresolved-attribute]
                do(_make_restrict_check_func(refs, resource_managers)).before(
                    ResourceAction.delete
                )
            )
