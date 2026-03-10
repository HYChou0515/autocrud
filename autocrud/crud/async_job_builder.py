"""Dynamic Job model builder for async create actions.

When a custom create action is registered with ``async_mode='job'``, the
framework needs a ``Job[PayloadType, ArtifactType]`` subclass to manage the
background work.  This module provides :func:`build_async_job_model` which
dynamically creates such a model at ``apply()`` time.

The generated model:

* Inherits from ``Job[PayloadType, dict]`` (artifact is a dict containing
  ``RevisionInfo``-like data).
* Has a ``_is_async_create_job = True`` class attribute for identification.
* Has a ``_target_resource_name`` attribute linking back to the parent resource.
* Is recognised by ``_is_job_subclass()`` via standard MRO checks.
"""

from __future__ import annotations

import re
import types
from typing import Any

import msgspec

from autocrud.types import Binary, Job

# ---------------------------------------------------------------------------
# UploadFile surrogate
# ---------------------------------------------------------------------------


class UploadFilePayload(msgspec.Struct):
    """Serialisable surrogate for ``fastapi.UploadFile`` in Job payloads.

    Uses :class:`~autocrud.types.Binary` to carry the file content and
    metadata (``data``, ``content_type``, ``size``), plus an extra
    ``filename`` field that ``Binary`` does not have.

    At **endpoint** time the wrapper reads the incoming file and stores its
    content in the ``binary`` field.  At **job-execution** time the
    framework reconstructs a real ``UploadFile`` from these fields before
    calling the user's handler.
    """

    binary: Binary
    filename: str | None = None


# ---------------------------------------------------------------------------
# Type resolution helpers
# ---------------------------------------------------------------------------


def _can_msgspec_encode(ann: Any) -> bool:
    """Return ``True`` if *ann* can be natively encoded by msgspec.

    We probe by creating a throwaway Struct with a single field of that
    type and attempting to generate a JSON schema.  If msgspec does not
    support the type it will raise.
    """
    try:
        tmp = msgspec.defstruct("_Probe", [("_x", ann)])
        msgspec.json.schema(tmp)
        return True
    except Exception:
        return False


def resolve_payload_field_type(raw_ann: Any) -> tuple[Any, str | None]:
    """Map a handler parameter type to a msgspec-serialisable equivalent.

    Returns:
        ``(serialisable_type, conversion_kind)`` where *conversion_kind* is
        ``None`` when the type can be used as-is, or one of:

        * ``'upload_file'`` — ``UploadFile`` → :class:`UploadFilePayload`
        * ``'pydantic'`` — Pydantic ``BaseModel`` →
          ``pydantic_to_struct(type)``
        * ``'to_str'`` — non-msgspec type (e.g. ``pydantic_core.Url``) →
          ``str``
    """
    from fastapi import UploadFile as _UploadFile

    # UploadFile → UploadFilePayload
    if isinstance(raw_ann, type) and issubclass(raw_ann, _UploadFile):
        return UploadFilePayload, "upload_file"

    # Pydantic BaseModel → convert to equivalent Struct
    try:
        from pydantic import BaseModel as _PydanticBase
    except ImportError:  # pragma: no cover
        _PydanticBase = None  # type: ignore[assignment,misc]

    if (
        _PydanticBase is not None
        and isinstance(raw_ann, type)
        and issubclass(raw_ann, _PydanticBase)
    ):
        from autocrud.resource_manager.pydantic_converter import pydantic_to_struct

        return pydantic_to_struct(raw_ann), "pydantic"

    # If msgspec can handle the type natively, use it as-is
    if _can_msgspec_encode(raw_ann):
        return raw_ann, None

    # Fallback: serialise as str (e.g. pydantic_core.Url, custom types)
    return str, "to_str"


def _clean_action_name(action_name: str) -> str:
    """Remove path template variables and normalise to a kebab-case identifier.

    Examples::

        >>> _clean_action_name("generate-article")
        'generate-article'
        >>> _clean_action_name("/{name}/new")
        'new'
        >>> _clean_action_name("/{id}")
        ''
    """
    cleaned = re.sub(r"\{[^}]*\}", "", action_name)
    cleaned = cleaned.replace("/", "-").strip("-")
    cleaned = re.sub(r"-+", "-", cleaned)
    return cleaned


def build_async_job_model(
    action_name: str,
    resource_name: str,
    payload_type: type,
) -> type:
    """Build a dynamic ``Job`` subclass for an async create action.

    The generated class inherits from ``Job[payload_type, dict]`` so it has
    all standard Job fields (``payload``, ``status``, ``errmsg``,
    ``artifact``, ``retries``, etc.) with the payload typed to the handler's
    input type.  The artifact type is ``dict`` to store ``RevisionInfo``-like
    data after the handler completes.

    Path template variables (e.g. ``{name}``) and slashes are stripped from
    *action_name* when forming the class name.

    Args:
        action_name: The action path (e.g. ``"generate-article"`` or
            ``"/{name}/new"``).
        resource_name: The parent resource name (e.g. ``"article"``).
        payload_type: The msgspec.Struct type of the handler's body parameter.

    Returns:
        A new ``Job`` subclass class.

    Example:
        >>> from msgspec import Struct
        >>> class Req(Struct):
        ...     prompt: str
        >>> JobModel = build_async_job_model("generate", "article", Req)
        >>> JobModel.__name__
        'GenerateArticleJob'
        >>> JobModel._is_async_create_job
        True
    """
    clean_name = _clean_action_name(action_name) or resource_name
    action_pascal = clean_name.replace("-", " ").title().replace(" ", "")
    resource_pascal = resource_name.replace("-", " ").title().replace(" ", "")
    class_name = f"{action_pascal}{resource_pascal}Job"

    # Create a Job subclass with concrete payload type and dict artifact
    job_model = types.new_class(class_name, (Job[payload_type, dict],), {})

    # Attach metadata for identification and linking
    job_model._is_async_create_job = True  # type: ignore[attr-defined]
    job_model._target_resource_name = resource_name  # type: ignore[attr-defined]
    job_model._action_name = action_name  # type: ignore[attr-defined]

    return job_model


def build_auto_payload_struct(
    action_name: str,
    resource_name: str,
    param_fields: list[tuple[str, type]],
) -> type:
    """Build a dynamic payload ``Struct`` from handler parameter types.

    When a create-action handler has no explicit ``msgspec.Struct`` body
    parameter — e.g. it only takes scalar query/path parameters — this
    function auto-generates a payload Struct so that all inputs can be
    captured inside a ``Job`` payload for async processing.

    Args:
        action_name: The action path (e.g. ``"create-character"``).
        resource_name: The parent resource name.
        param_fields: ``[(name, type), ...]`` for each serialisable parameter.

    Returns:
        A new ``msgspec.Struct`` subclass with fields matching the handler's
        parameters.
    """
    clean_name = _clean_action_name(action_name) or resource_name
    action_pascal = clean_name.replace("-", " ").title().replace(" ", "")
    resource_pascal = resource_name.replace("-", " ").title().replace(" ", "")
    class_name = f"{action_pascal}{resource_pascal}Payload"

    return msgspec.defstruct(class_name, param_fields)


def derive_job_resource_name(action_name: str, resource_name: str = "") -> str:
    """Derive the resource name for an auto-generated async Job model.

    Path template variables (e.g. ``{name}``) and slashes are stripped.
    If nothing remains, *resource_name* is used as a fallback.

    Args:
        action_name: The action path (e.g. ``"generate-article"`` or
            ``"/{name}/new"``).
        resource_name: Fallback when the cleaned action name is empty.

    Returns:
        The kebab-case resource name (e.g. ``"generate-article-job"``).
    """
    clean_name = _clean_action_name(action_name)
    if not clean_name:
        clean_name = resource_name or "unnamed"
    return f"{clean_name}-job"
