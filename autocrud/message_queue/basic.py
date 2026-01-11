from typing import Callable, Generic, TypeVar


from autocrud.types import (
    IMessageQueue,
    IResourceManager,
    Job,
    Resource,
    TaskStatus,
)

T = TypeVar("T")


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

    def set_resource_manager(self, resource_manager: IResourceManager[Job[T]]) -> None:
        """Set the resource manager for this message queue."""
        self._rm = resource_manager

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
        job.result = result

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
        job.result = error

        self.rm.create_or_update(resource_id, job)
        resource.data = job
        return resource

    def stop_consuming(self) -> None:
        """Stop consuming jobs from the queue."""
        pass
