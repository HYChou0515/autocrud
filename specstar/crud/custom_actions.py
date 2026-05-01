from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal


@dataclass
class _PendingCreateAction:
    """Metadata for a custom create action registered via @spec.create_action()."""

    resource_name: str
    path: str
    label: str
    handler: Callable
    async_mode: Literal["job", "background"] | None = None
    job_name: str | None = None


@dataclass
class _PendingUpdateAction:
    """Metadata for a custom update action registered via @spec.update_action()."""

    resource_name: str
    path: str
    label: str
    handler: Callable
    mode: Literal["update", "modify"] = "update"
    existing_param: str = "existing"
    info_param: str = "info"
    meta_param: str = "meta"
    async_mode: Literal["job", "background"] | None = None
    job_name: str | None = None


class LazyJobHandler:
    def __init__(self, factory):
        self._factory = factory
        self._handler = None

    def __call__(self, resource):
        if self._handler is None:
            self._handler = self._factory()
        return self._handler(resource)
