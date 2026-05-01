"""Async job model registration for SpecStar create / update actions.

Functions here are called by SpecStar during ``apply()`` to auto-register
Job models for ``async_mode='job'`` actions.  They take the relevant SpecStar
state as plain arguments and return the registry dicts that are stored back
on the SpecStar instance.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _reconstruct_params(kwargs: dict, conversions: dict[str, tuple[str, type]]) -> dict:
    """Reconstruct original param types from serialised surrogates.

    Conversion kinds:

    * ``'upload_file'`` — UploadFilePayload → ``starlette.datastructures.UploadFile``
    * ``'pydantic'`` — msgspec Struct → original Pydantic ``BaseModel``
    * ``'to_str'`` — ``str`` → attempt ``original_type(str_value)``
    """
    import io

    import msgspec as _ms

    from specstar.crud.async_job_builder import UploadFilePayload

    for field_name, (conv_kind, orig_type) in conversions.items():
        if field_name not in kwargs:
            continue
        val = kwargs[field_name]

        if conv_kind == "upload_file" and isinstance(val, UploadFilePayload):
            from starlette.datastructures import Headers
            from starlette.datastructures import UploadFile as _StarletteUpload

            binary = val.binary
            data = binary.data if not isinstance(binary.data, _ms.UnsetType) else b""
            ct = (
                binary.content_type
                if not isinstance(binary.content_type, _ms.UnsetType)
                else "application/octet-stream"
            )
            sz = binary.size if not isinstance(binary.size, _ms.UnsetType) else None
            kwargs[field_name] = _StarletteUpload(
                file=io.BytesIO(data),
                filename=val.filename,
                size=sz,
                headers=Headers({"content-type": ct}),
            )
        elif conv_kind == "pydantic":
            kwargs[field_name] = orig_type.model_validate(_ms.to_builtins(val))  # ty:ignore[unresolved-attribute]
        elif conv_kind == "to_str":
            try:
                kwargs[field_name] = orig_type(val)
            except Exception:
                pass

    return kwargs


def register_async_create_jobs(
    pending_actions: list,
    resource_managers: dict[str, Any],
    add_model: Callable,
) -> dict[int, tuple]:
    """Auto-register Job models for ``async_mode='job'`` create actions.

    Returns the registry mapping ``action handler id → (job_resource_name,
    job_model, target_rm, auto_payload_type, param_conversions)``.
    """
    import msgspec as _msgspec

    from specstar.crud.async_job_builder import (
        build_async_job_model,
        build_auto_payload_struct,
        derive_job_resource_name,
        resolve_payload_field_type,
    )
    from specstar.util.type_utils import unwrap_annotated

    registry: dict[int, tuple] = {}

    for action in pending_actions:
        if action.async_mode != "job":
            continue

        target_rm = resource_managers.get(action.resource_name)
        if target_rm is None:
            logger.warning(
                f"async create_action '{action.path}' targets resource "
                f"'{action.resource_name}' which is not registered. Skipping."
            )
            continue

        sig = inspect.signature(action.handler)
        payload_type = None
        auto_payload_type = None
        for name, param in sig.parameters.items():
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            raw_ann, _ = unwrap_annotated(ann)
            if isinstance(raw_ann, type) and issubclass(raw_ann, _msgspec.Struct):
                payload_type = raw_ann
                break

        if payload_type is None:
            param_fields: list[tuple[str, type]] = []
            param_conversions: dict[str, tuple[str, type]] = {}

            for pname, param in sig.parameters.items():
                ann = param.annotation
                if ann is inspect.Parameter.empty:
                    continue
                raw_ann, _ = unwrap_annotated(ann)

                ser_type, conv_kind = resolve_payload_field_type(raw_ann)
                param_fields.append((pname, ser_type))
                if conv_kind is not None:
                    param_conversions[pname] = (conv_kind, raw_ann)

            if not param_fields:
                logger.warning(
                    f"async create_action '{action.path}' handler has no "
                    f"parameters. Cannot generate Job model. "
                    f"Falling back to sync."
                )
                action.async_mode = None
                continue

            auto_payload_type = build_auto_payload_struct(
                action_name=action.path,
                resource_name=action.resource_name,
                param_fields=param_fields,
            )
            payload_type = auto_payload_type
        else:
            param_conversions = {}

        job_model = build_async_job_model(
            action_name=action.path,
            resource_name=action.resource_name,
            payload_type=payload_type,
        )
        job_resource_name = action.job_name or derive_job_resource_name(
            action.path, action.resource_name
        )

        original_handler = action.handler
        target_resource_manager = target_rm
        _is_auto_payload = auto_payload_type is not None

        def _make_job_handler(
            handler,
            trm,
            *,
            auto_payload=False,
            param_conversions=None,
            resource_managers=None,
            job_resource_name=None,
        ):
            """Create a closure to capture the right handler and target RM.

            Args:
                handler: The user's create-action function.
                trm: The target resource's ResourceManager.
                auto_payload: When ``True`` the payload is an auto-generated
                    Struct whose fields mirror the handler's parameters.
                    The handler is called with ``**kwargs`` instead of a
                    single positional Struct argument.
                param_conversions: Mapping of field name →
                    ``(conv_kind, original_type)`` for fields that need
                    reconstruction from their serialisable surrogates.
                resource_managers: The SpecStar resource_managers dict.
                    Used at job-execution time to restore ``Binary`` data.
                job_resource_name: Name of the job resource.
            """
            _is_async = inspect.iscoroutinefunction(handler)
            _conversions = param_conversions or {}
            _has_binary_conv = any(k == "upload_file" for k, _ in _conversions.values())
            _rms = resource_managers
            _jrn = job_resource_name

            def job_handler(resource, job_context=None):
                payload = resource.data.payload
                if auto_payload:
                    if _has_binary_conv and _rms and _jrn:
                        jrm = _rms.get(_jrn)
                        if jrm is not None:
                            restored = jrm.restore_binary(resource.data)
                            payload = restored.payload

                    kwargs = {f: getattr(payload, f) for f in payload.__struct_fields__}
                    if _conversions:
                        kwargs = _reconstruct_params(kwargs, _conversions)
                    raw_result = handler(**kwargs)
                else:
                    raw_result = handler(payload)

                if _is_async:
                    result = asyncio.run(raw_result)
                else:
                    result = raw_result

                if result is not None:
                    _job_user = resource.info.created_by or "system"
                    with trm.using(_job_user, dt.datetime.now()):
                        info = trm.create(result)
                    artifact = {
                        "resource_id": info.resource_id,
                        "revision_id": info.revision_id,
                        "resource_name": trm.resource_name,
                    }
                    if job_context is not None:
                        job_context.set_artifact(artifact)
                    else:
                        resource.data.artifact = artifact

            return job_handler

        wrapped_handler = _make_job_handler(
            original_handler,
            target_resource_manager,
            auto_payload=_is_auto_payload,
            param_conversions=param_conversions if _is_auto_payload else None,
            resource_managers=resource_managers,
            job_resource_name=job_resource_name,
        )

        add_model(
            job_model,
            name=job_resource_name,
            job_handler=wrapped_handler,
        )

        registry[id(action.handler)] = (
            job_resource_name,
            job_model,
            target_rm,
            auto_payload_type,
            param_conversions if _is_auto_payload else None,
        )

        job_rm = resource_managers[job_resource_name]
        target_rm.register_async_create_job(job_resource_name, job_rm)

    return registry


def register_async_update_jobs(
    pending_actions: list,
    resource_managers: dict[str, Any],
    add_model: Callable,
) -> dict[int, tuple]:
    """Auto-register Job models for ``async_mode='job'`` update actions.

    Returns the registry mapping ``action handler id → (job_resource_name,
    job_model, target_rm, auto_payload_type, param_conversions, update_mode,
    existing_param, info_param, meta_param)``.
    """
    import msgspec as _msgspec

    from specstar.crud.async_job_builder import (
        build_async_update_job_model,
        build_auto_payload_struct,
        derive_job_resource_name,
        resolve_payload_field_type,
    )
    from specstar.util.type_utils import unwrap_annotated

    registry: dict[int, tuple] = {}

    for action in pending_actions:
        if action.async_mode != "job":
            continue

        target_rm = resource_managers.get(action.resource_name)
        if target_rm is None:
            logger.warning(
                f"async update_action '{action.path}' targets resource "
                f"'{action.resource_name}' which is not registered. Skipping."
            )
            continue

        skip_params = {action.existing_param, action.info_param, action.meta_param}
        sig = inspect.signature(action.handler)
        payload_type = None
        auto_payload_type = None
        for name, param in sig.parameters.items():
            if name in skip_params:
                continue
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            raw_ann, _ = unwrap_annotated(ann)
            if isinstance(raw_ann, type) and issubclass(raw_ann, _msgspec.Struct):
                payload_type = raw_ann
                break

        if payload_type is None:
            param_fields: list[tuple[str, type]] = []
            param_conversions: dict[str, tuple[str, type]] = {}

            for pname, param in sig.parameters.items():
                if pname in skip_params:
                    continue
                ann = param.annotation
                if ann is inspect.Parameter.empty:
                    continue
                raw_ann, _ = unwrap_annotated(ann)

                ser_type, conv_kind = resolve_payload_field_type(raw_ann)
                param_fields.append((pname, ser_type))
                if conv_kind is not None:
                    param_conversions[pname] = (conv_kind, raw_ann)

            auto_payload_type = build_auto_payload_struct(
                action_name=action.path,
                resource_name=action.resource_name,
                param_fields=param_fields,
                extra_fields=[("resource_id", str)],
            )
            payload_type = auto_payload_type
        else:
            wrapper_fields = [
                ("resource_id", str),
                ("payload_data", payload_type),
            ]
            clean_name = action.path.replace("-", " ").title().replace(" ", "")
            resource_pascal = (
                action.resource_name.replace("-", " ").title().replace(" ", "")
            )
            wrapper_name = f"{clean_name}{resource_pascal}UpdatePayload"
            auto_payload_type = _msgspec.defstruct(wrapper_name, wrapper_fields)
            payload_type = auto_payload_type
            param_conversions = {}

        job_model = build_async_update_job_model(
            action_name=action.path,
            resource_name=action.resource_name,
            payload_type=payload_type,
            update_mode=action.mode,
        )
        job_resource_name = action.job_name or derive_job_resource_name(
            action.path, action.resource_name
        )

        original_handler = action.handler
        target_resource_manager = target_rm
        _is_auto_payload = auto_payload_type is not None
        _update_mode = action.mode
        _existing_param = action.existing_param
        _info_param = action.info_param
        _meta_param = action.meta_param

        def _make_update_job_handler(
            handler,
            trm,
            *,
            auto_payload=False,
            has_explicit_struct=False,
            param_conversions=None,
            resource_managers=None,
            job_resource_name=None,
            update_mode="update",
            existing_param="existing",
            info_param="info",
            meta_param="meta",
        ):
            _is_async = inspect.iscoroutinefunction(handler)
            _conversions = param_conversions or {}
            _has_binary_conv = any(k == "upload_file" for k, _ in _conversions.values())
            _rms = resource_managers
            _jrn = job_resource_name
            _sig = inspect.signature(handler)
            _has_existing = existing_param in _sig.parameters
            _has_info = info_param in _sig.parameters
            _has_meta = meta_param in _sig.parameters

            def job_handler(resource, job_context=None):
                payload = resource.data.payload
                _resource_id = payload.resource_id

                if has_explicit_struct:
                    kwargs = {
                        next(
                            (
                                n
                                for n in _sig.parameters
                                if n not in {existing_param, info_param, meta_param}
                                and isinstance(_sig.parameters[n].annotation, type)
                            ),
                            "body",
                        ): payload.payload_data
                    }
                elif auto_payload:
                    if _has_binary_conv and _rms and _jrn:
                        jrm = _rms.get(_jrn)
                        if jrm is not None:
                            restored = jrm.restore_binary(resource.data)
                            payload = restored.payload

                    kwargs = {
                        f: getattr(payload, f)
                        for f in payload.__struct_fields__
                        if f != "resource_id"
                    }
                    if _conversions:
                        kwargs = _reconstruct_params(kwargs, _conversions)
                else:
                    kwargs = {}

                _job_user = resource.info.created_by or "system"
                with trm.using(_job_user, dt.datetime.now()):
                    existing_resource = trm.get(_resource_id)
                if _has_existing:
                    kwargs[existing_param] = existing_resource.data
                if _has_info:
                    kwargs[info_param] = existing_resource.info
                if _has_meta:
                    with trm.using(_job_user, dt.datetime.now()):
                        kwargs[meta_param] = trm.get_meta(_resource_id)

                raw_result = handler(**kwargs)

                if _is_async:
                    result = asyncio.run(raw_result)
                else:
                    result = raw_result

                if result is not None:
                    with trm.using(_job_user, dt.datetime.now()):
                        if update_mode == "modify":
                            info = trm.modify(_resource_id, data=result)
                        else:
                            info = trm.update(_resource_id, result)
                    artifact = {
                        "resource_id": info.resource_id,
                        "revision_id": info.revision_id,
                        "resource_name": trm.resource_name,
                    }
                    if job_context is not None:
                        job_context.set_artifact(artifact)
                    else:
                        resource.data.artifact = artifact

            return job_handler

        _has_explicit_struct = False
        for _pname, _pparam in sig.parameters.items():
            if _pname in skip_params:
                continue
            _ann = _pparam.annotation
            if _ann is inspect.Parameter.empty:
                continue
            _raw_ann, _ = unwrap_annotated(_ann)
            if isinstance(_raw_ann, type) and issubclass(_raw_ann, _msgspec.Struct):
                _has_explicit_struct = True
                break

        wrapped_handler = _make_update_job_handler(
            original_handler,
            target_resource_manager,
            auto_payload=_is_auto_payload,
            has_explicit_struct=_has_explicit_struct,
            param_conversions=param_conversions if not _has_explicit_struct else None,
            resource_managers=resource_managers,
            job_resource_name=job_resource_name,
            update_mode=_update_mode,
            existing_param=_existing_param,
            info_param=_info_param,
            meta_param=_meta_param,
        )

        add_model(
            job_model,
            name=job_resource_name,
            job_handler=wrapped_handler,
        )

        registry[id(action.handler)] = (
            job_resource_name,
            job_model,
            target_rm,
            auto_payload_type,
            param_conversions if not _has_explicit_struct else None,
            action.mode,
            action.existing_param,
            action.info_param,
            action.meta_param,
        )

        job_rm = resource_managers[job_resource_name]
        target_rm.register_async_update_job(job_resource_name, job_rm)

    return registry
