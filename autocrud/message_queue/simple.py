from typing import TYPE_CHECKING, Callable, Generic, TypeVar


from autocrud.message_queue.basic import BasicMessageQueue
from autocrud.types import (
    DataSearchCondition,
    DataSearchOperator,
    IMessageQueueFactory,
    Job,
    Resource,
    ResourceDataSearchSort,
    ResourceMetaSearchQuery,
    ResourceMetaSearchSort,
    ResourceMetaSortDirection,
    ResourceMetaSortKey,
    TaskStatus,
)

if TYPE_CHECKING:
    from autocrud.types import IResourceManager

T = TypeVar("T")


class SimpleMessageQueue(BasicMessageQueue[T], Generic[T]):
    """
    A dedicated message queue that manages jobs as resources via ResourceManager.

    This allows jobs to have full versioning, permissions, and lifecycle management
    provided by AutoCRUD's ResourceManager.
    """

    def __init__(
        self,
        do: Callable[[Resource[Job[T]]], None],
        resource_manager: "IResourceManager[Job[T]]",
    ):
        super().__init__(do)
        self._rm = resource_manager
        self._running = False

    def put(self, resource_id: str) -> Resource[Job[T]]:
        """
        Enqueue a job that has already been created.

        Args:
            resource_id: The ID of the job resource that was already created.

        Returns:
            The job resource.
        """
        # The job resource is already created by rm.create()
        # Just return it for confirmation
        return self.rm.get(resource_id)

    def pop(self) -> Resource[Job[T]] | None:
        """
        Dequeue the next pending job and mark it as processing.

        Returns:
            The job resource if one is available, None otherwise.
        """
        # Find next pending job, ordered by retries (fewer first), then creation time (FIFO)
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="status",
                    operator=DataSearchOperator.equals,
                    value=TaskStatus.PENDING,
                )
            ],
            sorts=[
                ResourceDataSearchSort(
                    field_path="retries",
                    direction=ResourceMetaSortDirection.ascending,
                ),
                ResourceMetaSearchSort(
                    key=ResourceMetaSortKey.created_time,
                    direction=ResourceMetaSortDirection.ascending,
                ),
            ],
            limit=1,
        )

        metas = self.rm.search_resources(query)

        for meta in metas:
            try:
                # Optimistic locking via revision check could be implemented here
                # if ResourceManager supported atomic find-and-update.
                # For now, we fetch, check status, and update.
                with self._rm_meta_provide(meta.created_by):
                    resource = self.rm.get(meta.resource_id)

                if resource.data.status != TaskStatus.PENDING:
                    continue

                # Update status to processing
                updated_job = resource.data
                updated_job.status = TaskStatus.PROCESSING

                # Update revision
                with self._rm_meta_provide(meta.created_by):
                    self.rm.create_or_update(resource.info.resource_id, updated_job)

                # Return the updated resource
                resource.data = updated_job
                return resource
            except Exception:
                # If update fails (e.g. concurrent modification or deletion), try next
                continue

        return None

    def start_consume(self) -> None:
        """Start consuming jobs from the queue."""
        import time

        self._running = True
        while self._running:
            job = self.pop()
            if job:
                try:
                    self._do(job)
                    self.complete(job.info.resource_id)
                except Exception as e:
                    # Update Job with error message and retry count
                    error_msg = str(e)
                    updated_job = job.data
                    updated_job.status = TaskStatus.FAILED
                    updated_job.errmsg = error_msg
                    updated_job.retries += 1

                    try:
                        with self._rm_meta_provide(job.info.created_by):
                            self.rm.create_or_update(job.info.resource_id, updated_job)
                    except Exception:
                        # If update fails, still mark as failed via fail()
                        pass

                    self.fail(job.info.resource_id, error_msg)
            else:
                time.sleep(0.1)

    def stop_consuming(self):
        """Stop the consumption loop."""
        self._running = False


class SimpleMessageQueueFactory(IMessageQueueFactory):
    """Factory for creating SimpleMessageQueue instances."""

    def build(
        self, do: Callable[[Resource[Job[T]]], None]
    ) -> Callable[["IResourceManager[Job[T]]"], SimpleMessageQueue[T]]:
        """Build a SimpleMessageQueue factory function.

        Args:
            do: Callback function to process each job.

        Returns:
            A callable that accepts an IResourceManager and returns a SimpleMessageQueue instance.
        """

        def create_queue(
            resource_manager: "IResourceManager[Job[T]]",
        ) -> SimpleMessageQueue[T]:
            return SimpleMessageQueue(do, resource_manager)

        return create_queue
