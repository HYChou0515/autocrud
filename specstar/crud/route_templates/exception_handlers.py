"""Shared exception-to-HTTP mapping for route templates.

Provides a single :func:`to_http_exception` helper that maps internal
domain exceptions to consistent :class:`~fastapi.HTTPException` responses.

Every route handler should use the same pattern::

    except Exception as e:
        raise to_http_exception(e)

Mapping table:

==================================  ====
Exception                           HTTP
==================================  ====
``HTTPException``                   (re-raised as-is)
``msgspec.ValidationError``         422
``specstar.types.ValidationError``  422
``PermissionDeniedError``           403
``ResourceIsDeletedError``          410
``ResourceNotFoundError`` family    404
``FileNotFoundError``               404
``ResourceConflictError`` family    409
``NotImplementedError``             501
fallback                            400
==================================  ====
"""

import msgspec
from fastapi import HTTPException

from specstar.types import (
    PermissionDeniedError,
    ResourceConflictError,
    ResourceIsDeletedError,
    ResourceNotFoundError,
    UniqueConstraintError,
    ValidationError,
)


def to_http_exception(e: Exception) -> HTTPException:
    """Convert a domain exception to an appropriate :class:`HTTPException`.

    This centralises the error→HTTP-status mapping so that every route
    template returns consistent status codes for the same logical error.

    If *e* is already an :class:`HTTPException` it is returned unchanged
    so that inline ``raise HTTPException(...)`` inside a ``try`` block
    passes through transparently.

    Args:
        e: The caught exception.

    Returns:
        An :class:`HTTPException` with the mapped status code and the
        original exception message as ``detail``.

    Examples:
        >>> from specstar.types import ResourceIDNotFoundError
        >>> exc = to_http_exception(ResourceIDNotFoundError("abc"))
        >>> exc.status_code
        404

        >>> exc = to_http_exception(ValueError("bad input"))
        >>> exc.status_code
        400
    """
    # Already an HTTPException — pass through unchanged
    if isinstance(e, HTTPException):
        return e

    # Validation errors (both msgspec type-level and specstar custom)
    if isinstance(e, (msgspec.ValidationError, ValidationError)):
        return HTTPException(status_code=422, detail=str(e))

    # Permission denied
    if isinstance(e, PermissionDeniedError):
        return HTTPException(status_code=403, detail=str(e))

    # Soft-deleted: 410 Gone, distinct from "never existed" 404.
    # Must be checked before ResourceNotFoundError since it is a subclass.
    if isinstance(e, ResourceIsDeletedError):
        return HTTPException(status_code=410, detail=str(e))

    # Resource / revision not found
    if isinstance(e, ResourceNotFoundError):
        return HTTPException(status_code=404, detail=str(e))

    # File not found (e.g. blob storage)
    if isinstance(e, FileNotFoundError):
        return HTTPException(status_code=404, detail=str(e) or "Not found")

    # Unique constraint violations get structured detail
    if isinstance(e, UniqueConstraintError):
        return HTTPException(
            status_code=409,
            detail={
                "message": str(e),
                "field": e.field,
                "conflicting_resource_id": e.conflicting_resource_id,
            },
        )

    # Other conflict errors (DuplicateResourceError, SchemaConflictError, etc.)
    if isinstance(e, ResourceConflictError):
        return HTTPException(status_code=409, detail=str(e))

    # Not implemented (e.g. blob store not configured)
    if isinstance(e, NotImplementedError):
        return HTTPException(status_code=501, detail=str(e) or "Not implemented")

    # Fallback — generic bad request
    return HTTPException(status_code=400, detail=str(e))
