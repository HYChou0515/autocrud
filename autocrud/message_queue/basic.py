import datetime as dt
from abc import abstractmethod
from typing import Callable, Generic, TypeVar

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


class DelayRetry(Exception):
    """Indicates that a job should be delayed and retried after a specified interval.

    This exception allows the job handler to trigger a delayed retry by raising
    DelayRetry(delay_seconds). The job will be marked as COMPLETED and re-enqueued
    to run again after the specified delay.

    Args:
        delay_seconds: Number of seconds to wait before retrying the job.

    Example:
        ```python
        def process_job(resource: Resource[Job[MyTask]]):
            if should_wait():
                raise DelayRetry(60)  # Retry after 60 seconds
            # Process normally
        ```
    """

    def __init__(self, delay_seconds: int):
        self.delay_seconds = delay_seconds
        super().__init__(f"Job will be retried after {delay_seconds} seconds")


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


class DelayableMessageQueue(BasicMessageQueue[T], Generic[T]):
    """
    Base class for message queues that support delayed job execution.

    This class provides common functionality for:
    - Initial delay before first execution (periodic_initial_delay_seconds)
    - Periodic job execution (periodic_interval_seconds, periodic_max_runs)
    - DelayRetry exception handling

    Subclasses must implement:
    - _schedule_delayed_job(resource_id, delay_seconds): Schedule a job for delayed execution
    """

    @abstractmethod
    def _schedule_delayed_job(self, resource_id: str, delay_seconds: int) -> None:
        """
        Schedule a job for delayed execution.

        This method must be implemented by subclasses to handle the actual
        scheduling mechanism (e.g., RabbitMQ delay queue, in-memory scheduler).

        Args:
            resource_id: The ID of the job resource to schedule
            delay_seconds: Number of seconds to delay before execution
        """
        pass

    def _should_apply_initial_delay(self, job: Job[T]) -> bool:
        """
        Check if initial delay should be applied to a job.

        Args:
            job: The job to check

        Returns:
            True if initial delay should be applied, False otherwise
        """
        return (
            job.periodic_initial_delay_seconds is not None
            and job.periodic_initial_delay_seconds > 0
            and job.periodic_runs == 0  # Only apply on first run
        )

    def _handle_periodic_job(
        self,
        resource_id: str,
        completed_resource: Resource[Job[T]],
        user_requested_stop: bool = False,
    ) -> None:
        """
        Handle periodic job logic after successful execution.

        This method:
        1. Increments periodic_runs count
        2. Determines if job should continue running
        3. Schedules next run or updates final state

        Args:
            resource_id: The ID of the job resource
            completed_resource: The completed job resource
            user_requested_stop: Whether user requested to stop (callback returned False)
        """
        job = completed_resource.data

        # Check if this is a periodic job
        if job.periodic_interval_seconds is None or job.periodic_interval_seconds <= 0:
            return  # Not a periodic job

        # Increment run count first (always, even if user requested stop)
        job.periodic_runs += 1

        # Check if we should continue running (after incrementing)
        # Stop if: user requested stop OR reached max runs
        should_continue = not user_requested_stop and (
            job.periodic_max_runs is None or job.periodic_runs < job.periodic_max_runs
        )

        if should_continue:
            # Reset retry count for next run, but keep status as COMPLETED
            job.retries = 0
            with self._rm_meta_provide(completed_resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

            # Schedule next run
            self._schedule_delayed_job(resource_id, job.periodic_interval_seconds)
        else:
            # Reached max runs, just update the periodic_runs count
            with self._rm_meta_provide(completed_resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

    def _handle_delay_retry(
        self, resource_id: str, delay_seconds: int, created_by: str
    ) -> None:
        """
        Handle DelayRetry exception.

        This method:
        1. Completes the job (marks as COMPLETED)
        2. Resets retry count to 0
        3. Schedules the job for delayed re-execution

        Args:
            resource_id: The ID of the job resource
            delay_seconds: Number of seconds to delay before retry
            created_by: The user who created the job
        """
        # Complete the job
        completed_resource = self.complete(resource_id)
        job_data = completed_resource.data

        # Reset retry count
        job_data.retries = 0
        with self._rm_meta_provide(created_by):
            self.rm.create_or_update(resource_id, job_data)

        # Schedule delayed retry
        self._schedule_delayed_job(resource_id, delay_seconds)
