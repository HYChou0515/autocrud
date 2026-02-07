import datetime as dt
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from autocrud.message_queue.basic import DelayableMessageQueue, DelayRetry, NoRetry
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


class SimpleMessageQueue(DelayableMessageQueue[T], Generic[T]):
    """
    A dedicated message queue that manages jobs as resources via ResourceManager.

    This allows jobs to have full versioning, permissions, and lifecycle management
    provided by AutoCRUD's ResourceManager.

    Features:
    - Automatic retry on failure
    - Configurable max retry count
    - NoRetry exception support to skip retries
    """

    def __init__(
        self,
        do: Callable[[Resource[Job[T]]], None],
        resource_manager: "IResourceManager[Job[T]]",
        max_retries: int = 3,
    ):
        super().__init__(do)
        self._rm = resource_manager
        self._running = False
        self.max_retries = max_retries
        # Track periodic jobs: {resource_id: next_run_time}
        self._periodic_schedule: dict[str, dt.datetime] = {}

    def put(self, resource_id: str) -> Resource[Job[T]]:
        """
        Enqueue a job that has already been created.

        Args:
            resource_id: The ID of the job resource that was already created.

        Returns:
            The job resource.
        """
        # The job resource is already created by rm.create()
        resource = self.rm.get(resource_id)
        job = resource.data

        # Check if job has initial delay configured
        if self._should_apply_initial_delay(job):
            # Set status to COMPLETED so pop() won't pick it up immediately
            # _check_periodic_jobs will set it back to PENDING when ready
            job.status = TaskStatus.COMPLETED
            with self._rm_meta_provide(resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

            # Schedule for delayed execution
            self._schedule_delayed_job(resource_id, job.periodic_initial_delay_seconds)
        # else: job remains PENDING and will be picked up by pop() immediately

        return resource

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

    def _schedule_periodic_job(self, resource_id: str, interval_seconds: int) -> None:
        """
        Schedule a periodic job for re-execution.

        Args:
            resource_id: The resource identifier
            interval_seconds: Delay before re-execution in seconds
        """
        next_run_time = dt.datetime.now() + dt.timedelta(seconds=interval_seconds)
        self._periodic_schedule[resource_id] = next_run_time

    def _schedule_delayed_job(self, resource_id: str, delay_seconds: int) -> None:
        """
        Implementation of abstract method from DelayableMessageQueue.

        Schedules a job for delayed execution using the periodic job mechanism.

        Args:
            resource_id: The ID of the job resource to schedule
            delay_seconds: Number of seconds to delay before execution
        """
        self._schedule_periodic_job(resource_id, delay_seconds)

    def _check_periodic_jobs(self) -> None:
        """
        Check for periodic jobs that are ready to run and re-enqueue them.
        """
        now = dt.datetime.now()
        ready_jobs = [
            resource_id
            for resource_id, next_run_time in self._periodic_schedule.items()
            if next_run_time <= now
        ]

        for resource_id in ready_jobs:
            # Remove from schedule
            del self._periodic_schedule[resource_id]

            # Update job status to PENDING so it gets picked up
            try:
                resource = self.rm.get(resource_id)
                job = resource.data
                job.status = TaskStatus.PENDING
                with self._rm_meta_provide(resource.info.created_by):
                    self.rm.create_or_update(resource_id, job)
            except Exception:
                # If update fails, just skip this job
                pass

    def _execute_job(self, job: Resource[Job[T]]) -> None:
        """
        Execute a job and handle success, DelayRetry, or failure.

        Args:
            job: The job resource to execute
        """
        try:
            result = self._do(job)
            # Check if callback explicitly requested to stop periodic execution
            user_requested_stop = result is False

            completed_job = self.complete(job.info.resource_id)

            # Handle periodic job using parent class method
            self._handle_periodic_job(
                job.info.resource_id, completed_job, user_requested_stop
            )

        except DelayRetry as e:
            # Handle DelayRetry using parent class method
            self._handle_delay_retry(
                job.info.resource_id, e.delay_seconds, job.info.created_by
            )

        except Exception as e:
            # Update Job with error message and retry count
            error_msg = str(e)
            updated_job = job.data
            updated_job.errmsg = error_msg
            updated_job.retries += 1

            # Check if we should retry or fail permanently
            should_retry = (
                not isinstance(e, NoRetry) and updated_job.retries <= self.max_retries
            )

            if should_retry:
                # Retry: set status back to PENDING
                updated_job.status = TaskStatus.PENDING
            else:
                # No retry: mark as permanently FAILED
                updated_job.status = TaskStatus.FAILED

            try:
                with self._rm_meta_provide(job.info.created_by):
                    self.rm.create_or_update(job.info.resource_id, updated_job)
            except Exception:
                # If update fails, still mark as failed via fail()
                pass

            # If not retrying, also call fail() to ensure consistent state
            if not should_retry:
                self.fail(job.info.resource_id, error_msg)

    def start_consume(self) -> None:
        """Start consuming jobs from the queue."""
        import time

        self._running = True
        while self._running:
            # Check for periodic jobs ready to run
            self._check_periodic_jobs()

            job = self.pop()
            if job:
                self._execute_job(job)
            else:
                time.sleep(0.1)

    def stop_consuming(self):
        """Stop the consumption loop."""
        self._running = False


class SimpleMessageQueueFactory(IMessageQueueFactory):
    """Factory for creating SimpleMessageQueue instances."""

    def __init__(self, max_retries: int = 3):
        """
        Initialize the factory.

        Args:
            max_retries: Maximum number of retries for failed jobs.
        """
        self.max_retries = max_retries

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
            return SimpleMessageQueue(
                do, resource_manager, max_retries=self.max_retries
            )

        return create_queue
