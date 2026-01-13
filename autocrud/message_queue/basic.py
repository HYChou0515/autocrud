from typing import Callable, Generic, TypeVar

import datetime as dt
from autocrud.types import (
    IMessageQueue,
    IResourceManager,
    Job,
    Resource,
    TaskStatus,
)

T = TypeVar("T")


class NoRetry(Exception):
    """Indicates that a job should not be retried."""

    pass


class BasicMessageQueue(IMessageQueue[T], Generic[T]):
    """
    A dedicated message queue that manages jobs as resources via ResourceManager.

    This allows jobs to have full versioning, permissions, and lifecycle management
    provided by AutoCRUD's ResourceManager.
    """

    def __init__(self, do: Callable[[Resource[Job[T]]], None]):
        self._rm: IResourceManager[Job[T]] | None = None
        self._do = do

    @property
    def rm(self) -> IResourceManager[Job[T]]:
        """The associated ResourceManager."""
        if self._rm is None:
            raise RuntimeError(
                "ResourceManager has not been set. "
                "Call set_resource_manager() before using the message queue."
            )
        return self._rm

    def _rm_meta_provide(self, user: str):
        """Helper to provide meta context for ResourceManager operations."""
        return self.rm.meta_provide(
            now=self.rm.now_or_unset or dt.datetime.now(),
            user=self.rm.user_or_unset or user,
        )

    def complete(self, resource_id: str, result: str | None = None) -> Resource[Job[T]]:
        """
        Mark a job as completed.

        Args:
            resource_id: The ID of the job resource.
            result: Optional result string.
        """
        resource = self.rm.get(resource_id)
        job = resource.data
        job.status = TaskStatus.COMPLETED
        job.errmsg = result

        with self._rm_meta_provide(resource.info.created_by):
            self.rm.create_or_update(resource_id, job)
        resource.data = job
        return resource

    def fail(self, resource_id: str, error: str) -> Resource[Job[T]]:
        """
        Mark a job as failed.

        Args:
            resource_id: The ID of the job resource.
            error: Error message.
        """
        resource = self.rm.get(resource_id)
        job = resource.data
        job.status = TaskStatus.FAILED
        job.errmsg = error

        with self._rm_meta_provide(resource.info.created_by):
            self.rm.create_or_update(resource_id, job)
        resource.data = job
        return resource

    def stop_consuming(self) -> None:
        """Stop consuming jobs from the queue."""
        pass
