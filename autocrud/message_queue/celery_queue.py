from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from autocrud.message_queue.basic import DelayableMessageQueue, DelayRetry, NoRetry
from autocrud.types import Job, Resource, TaskStatus

try:
    from celery import Celery
    from celery.exceptions import Ignore
except ImportError:
    Celery = None  # type: ignore
    Ignore = None  # type: ignore

if TYPE_CHECKING:
    from celery import Celery, Task
    from celery.exceptions import Ignore

    from autocrud.types import IResourceManager

T = TypeVar("T")


class CeleryMessageQueue(DelayableMessageQueue[T], Generic[T]):
    """
    Celery-based Message Queue implementation.

    This implementation uses Celery for distributed task execution and scheduling,
    while using AutoCRUD ResourceManager for payload storage and status persistence.

    Features:
    - Automatic retry on failure with configurable delay
    - Support for periodic tasks with configurable intervals
    - Support for delayed task execution
    - Distributed task execution via Celery workers

    Example:
        ```python
        from celery import Celery

        celery_app = Celery("autocrud", broker="redis://localhost:6379/0")


        def process_task(resource: Resource[Job[MyTask]]):
            # Process the task
            pass


        queue = CeleryMessageQueue(
            do=process_task,
            resource_manager=my_resource_manager,
            celery_app=celery_app,
            max_retries=3,
            retry_delay_seconds=10,
        )
        ```
    """

    def __init__(
        self,
        do: Callable[[Resource[Job[T]]], None],
        resource_manager: "IResourceManager[Job[T]]",
        celery_app: Celery,
        queue_name: str | None = None,
        max_retries: int = 3,
        retry_delay_seconds: int = 10,
    ):
        """Initialize the Celery message queue.

        Args:
            do: Callback function to process each job.
            resource_manager: ResourceManager for job persistence.
            celery_app: Celery application instance.
            queue_name: Optional queue name. If not provided, uses resource name.
            max_retries: Maximum number of retries for failed jobs (default: 3).
            retry_delay_seconds: Delay in seconds before retrying a failed job (default: 10).
        """
        if Celery is None:
            raise ImportError(
                "The 'celery' package is required for CeleryMessageQueue. "
                "Install it via 'pip install celery'"
            )

        super().__init__(do)
        self._rm = resource_manager
        self.celery_app = celery_app
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

        # Determine queue name from resource manager if not provided
        if queue_name is None:
            queue_name = f"autocrud.{resource_manager.resource_name}"
        self.queue_name = queue_name

        # Flag to control worker stopping
        self._should_stop = False
        self._worker_thread = None

        # Special marker for stopping workers (poison pill pattern)
        self._STOP_MARKER = "__CELERY_STOP_WORKER__"

        # Register the task with Celery
        self._register_task()

    def _register_task(self):
        """Register the job processing task with Celery."""

        # Create a reference to self for use in the task
        queue = self

        @self.celery_app.task(
            name=f"{self.queue_name}.process_job",
            bind=True,
            max_retries=self.max_retries,
            default_retry_delay=self.retry_delay_seconds,
        )
        def process_job_task(
            task_self: Task, resource_id: str, retry_count: int = 0
        ) -> None:
            """Celery task that processes a job resource.

            Args:
                task_self: The Celery task instance (bound).
                resource_id: The ID of the job resource to process.
                retry_count: Current retry count.
            """
            # Check for poison pill (stop marker)
            if resource_id == queue._STOP_MARKER:
                # Worker received stop signal, terminate gracefully
                raise Ignore()  # Stop processing without retry

            try:
                # 1. Fetch resource and update status to PROCESSING
                resource = queue.rm.get(resource_id)
                job = resource.data
                job.status = TaskStatus.PROCESSING
                with queue._rm_meta_provide(resource.info.created_by):
                    queue.rm.create_or_update(resource_id, job)
                resource.data = job

                # 2. Execute user callback
                result = queue._do(resource)

                # Check if callback explicitly requested to stop periodic execution
                user_requested_stop = result is False

                # 3. Mark as completed
                completed_resource = queue.complete(resource_id)

                # 4. Handle periodic job logic
                queue._handle_periodic_job(
                    resource_id, completed_resource, user_requested_stop
                )

            except DelayRetry as e:
                # Handle delayed retry
                queue._handle_delay_retry(
                    resource_id, e.delay_seconds, resource.info.created_by
                )
                # Stop Celery's own retry mechanism
                raise Ignore()

            except NoRetry as e:
                # Mark as failed without retry
                error_msg = str(e)
                resource = queue.rm.get(resource_id)
                job = resource.data
                job.status = TaskStatus.FAILED
                job.errmsg = error_msg
                job.retries = retry_count + 1
                with queue._rm_meta_provide(resource.info.created_by):
                    queue.rm.create_or_update(resource_id, job)
                # Stop Celery's own retry mechanism
                raise Ignore()

            except Exception as e:
                # Update job with error
                error_msg = str(e)
                try:
                    resource = queue.rm.get(resource_id)
                    job = resource.data
                    job.status = TaskStatus.FAILED
                    job.errmsg = error_msg
                    job.retries = retry_count + 1
                    with queue._rm_meta_provide(resource.info.created_by):
                        queue.rm.create_or_update(resource_id, job)
                except Exception:
                    # If we can't update, just continue with retry
                    pass

                # Retry using Celery's mechanism if retries remain
                if retry_count < queue.max_retries:
                    raise task_self.retry(
                        exc=e,
                        countdown=queue.retry_delay_seconds,
                        args=(resource_id, retry_count + 1),
                    )
                else:
                    # Max retries exceeded, stop retrying
                    raise Ignore()

        # Store task reference
        self._celery_task = process_job_task

    def put(self, resource_id: str) -> Resource[Job[T]]:
        """
        Enqueue a job that has already been created.

        Args:
            resource_id: The ID of the job resource that was already created.

        Returns:
            The job resource.
        """
        resource = self.rm.get(resource_id)
        job = resource.data

        # Check if job has initial delay configured
        if self._should_apply_initial_delay(job):
            # Schedule with initial delay
            self._celery_task.apply_async(
                args=(resource_id,),
                countdown=job.periodic_initial_delay_seconds,
                queue=self.queue_name,
            )
        else:
            # Enqueue immediately
            self._celery_task.apply_async(
                args=(resource_id,),
                queue=self.queue_name,
            )

        return resource

    def pop(self) -> Resource[Job[T]] | None:
        """
        Pop operation is not directly supported in Celery.

        Celery uses a worker-based model where tasks are automatically distributed
        to workers. Use start_consume() to start workers instead.

        Raises:
            NotImplementedError: This operation is not supported in Celery mode.
        """
        raise NotImplementedError(
            "pop() is not supported in CeleryMessageQueue. "
            "Use start_consume() to start Celery workers, or use the Celery CLI."
        )

    def _schedule_delayed_job(self, resource_id: str, delay_seconds: int) -> None:
        """
        Schedule a job for delayed execution using Celery's countdown.

        Args:
            resource_id: The ID of the job resource to schedule.
            delay_seconds: Number of seconds to delay before execution.
        """
        self._celery_task.apply_async(
            args=(resource_id,),
            countdown=delay_seconds,
            queue=self.queue_name,
        )

    def start_consume(self) -> None:
        """
        Start consuming jobs from the queue.

        This starts a Celery worker programmatically. For production use,
        it's recommended to use the Celery CLI instead:
            celery -A your_app worker --loglevel=info -Q {queue_name}

        Note: This method blocks and runs the worker in the current process.
        In eager mode (task_always_eager=True), worker runs until stop_consuming() is called.
        """
        # Reset stop flag
        self._should_stop = False

        # Check if we're in eager mode
        is_eager = getattr(self.celery_app.conf, "task_always_eager", False)

        if is_eager:
            # In eager mode, tasks execute synchronously on put()
            # We just need to keep the process alive until stop_consuming() is called
            import time

            while not self._should_stop:
                time.sleep(0.1)
        else:
            # Start worker programmatically for real broker
            argv = [
                "worker",
                "--loglevel=info",
                f"--queues={self.queue_name}",
                "--concurrency=1",
            ]
            self.celery_app.worker_main(argv)

    def _handle_periodic_job(
        self,
        resource_id: str,
        completed_resource: Resource[Job[T]],
        user_requested_stop: bool = False,
    ) -> None:
        """
        Handle periodic job logic after successful execution.

        Override parent method to check _should_stop flag before scheduling next run.
        This prevents infinite execution in eager mode when stop_consuming() is called.

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
        # Stop if: stop_consuming() was called OR user requested stop OR reached max runs
        should_continue = (
            not self._should_stop
            and not user_requested_stop
            and (
                job.periodic_max_runs is None
                or job.periodic_runs < job.periodic_max_runs
            )
        )

        if should_continue:
            # Reset retry count for next run, but keep status as COMPLETED
            job.retries = 0
            with self._rm_meta_provide(completed_resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

            # Schedule next run
            self._schedule_delayed_job(resource_id, job.periodic_interval_seconds)
        else:
            # Reached max runs or stop requested, just update the periodic_runs count
            with self._rm_meta_provide(completed_resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

    def stop_consuming(self) -> None:
        """
        Stop the Celery worker using poison pill pattern.

        Sends a special stop marker to the queue. When workers process this marker,
        they will terminate gracefully without rescheduling.
        """
        # Set stop flag (used by periodic job scheduling)
        self._should_stop = True

        # Send poison pill to stop workers
        try:
            self._celery_task.apply_async(
                args=(self._STOP_MARKER,),
                queue=self.queue_name,
            )
        except Exception:
            pass  # If enqueueing fails, that's ok

        # Also try to cancel consumers (for real workers)
        try:
            self.celery_app.control.cancel_consumer(self.queue_name)
        except Exception:
            pass


class CeleryMessageQueueFactory:
    """Factory for creating CeleryMessageQueue instances."""

    def __init__(
        self,
        celery_app: "Celery",
        queue_prefix: str = "autocrud.",
        max_retries: int = 3,
        retry_delay_seconds: int = 10,
    ):
        """Initialize the Celery message queue factory.

        Args:
            celery_app: Celery application instance.
            queue_prefix: Prefix for queue names (default: "autocrud.").
            max_retries: Maximum number of retries for failed jobs (default: 3).
            retry_delay_seconds: Delay in seconds before retrying a failed job (default: 10).
        """
        self.celery_app = celery_app
        self.queue_prefix = queue_prefix
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

    def build(
        self, do: Callable[[Resource[Job[T]]], None]
    ) -> Callable[["IResourceManager[Job[T]]"], CeleryMessageQueue[T]]:
        """Build a CeleryMessageQueue factory function.

        Args:
            do: Callback function to process each job.

        Returns:
            A callable that accepts an IResourceManager and returns a CeleryMessageQueue instance.
        """

        def create_queue(
            resource_manager: "IResourceManager[Job[T]]",
        ) -> CeleryMessageQueue[T]:
            queue_name = f"{self.queue_prefix}{resource_manager.resource_name}"
            return CeleryMessageQueue(
                do=do,
                resource_manager=resource_manager,
                celery_app=self.celery_app,
                queue_name=queue_name,
                max_retries=self.max_retries,
                retry_delay_seconds=self.retry_delay_seconds,
            )

        return create_queue
