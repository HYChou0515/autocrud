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
    RevisionStatus,
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
    - Configurable max retry count (queue-level default, per-job override)
    - NoRetry exception support to skip retries

    Per-job ``max_retries``:
        Each :class:`~autocrud.types.Job` may set its own ``max_retries``.
        When present (not ``None``), it overrides this queue's default.
        The per-job value is **not** capped — it may be larger than the
        queue default.
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

                # Update revision as draft so heartbeat can use modify()
                with self._rm_meta_provide(meta.created_by):
                    self.rm.create_or_update(
                        resource.info.resource_id,
                        updated_job,
                        status=RevisionStatus.draft,
                    )

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

        A HeartbeatThread runs in the background during execution so that
        ``recover_stale_jobs`` can distinguish live workers from dead ones.
        A LogFlushThread periodically persists execution logs to the blob store.

        Args:
            job: The job resource to execute
        """
        from autocrud.message_queue.context import JobContext
        from autocrud.message_queue.heartbeat import HeartbeatThread
        from autocrud.message_queue.log_flush import LogFlushThread

        resource_id = job.info.resource_id
        ctx = JobContext(job)
        ctx.info("Job started")

        hb = HeartbeatThread(
            mq=self,
            resource_id=resource_id,
            interval_seconds=self._heartbeat_interval,
        )
        hb.start()

        # Start log flush thread if blob store is available
        blob_store = self._blob_store
        log_key = self._log_key(resource_id)
        lf: LogFlushThread | None = None
        if blob_store is not None:
            lf = LogFlushThread(
                ctx=ctx,
                blob_store=blob_store,
                key=log_key,
                interval_seconds=10.0,
            )
            lf.start()

        try:
            self._execute_job_inner(job, ctx)
        finally:
            hb.stop()
            if lf is not None:
                lf.stop()  # stop() does a final flush

    def _execute_job_inner(self, job: Resource[Job[T]], ctx=None) -> None:
        """Core job execution logic (without heartbeat management).

        Args:
            job: The job resource to execute.
            ctx: Optional :class:`JobContext` for lifecycle logging.
        """
        try:
            result = self._invoke_handler(job, ctx)
            # Check if callback explicitly requested to stop periodic execution
            user_requested_stop = result is False

            if ctx is not None:
                ctx.info("Job completed")

            completed_job = self.complete(
                job.info.resource_id, _artifact=job.data.artifact
            )

            # Handle periodic job using parent class method
            self._handle_periodic_job(
                job.info.resource_id, completed_job, user_requested_stop
            )

        except DelayRetry as e:
            if ctx is not None:
                ctx.info(f"Job delayed retry: {e.delay_seconds}s")
            # Handle DelayRetry using parent class method
            self._handle_delay_retry(
                job.info.resource_id, e.delay_seconds, job.info.created_by
            )

        except Exception as e:
            # Update Job with error message and retry count
            error_msg = str(e)

            # Always log the error so operators can diagnose failures.
            if ctx is not None:
                ctx.error(f"Job error: {error_msg}")

            # Re-fetch from storage to avoid serialization issues
            # (the in-memory job may contain handler-set fields that
            # don't match the registered type, e.g. artifact on a
            # Job[T] without D).
            try:
                updated_job = self.rm.get(job.info.resource_id).data
            except Exception:
                updated_job = job.data
            updated_job.errmsg = error_msg
            updated_job.retries += 1

            # Check if we should retry or fail permanently.
            # Per-job max_retries takes precedence over the queue default.
            effective_max_retries = (
                updated_job.max_retries
                if updated_job.max_retries is not None
                else self.max_retries
            )
            should_retry = (
                not isinstance(e, NoRetry)
                and updated_job.retries <= effective_max_retries
            )

            if should_retry:
                # Retry: set status back to PENDING
                updated_job.status = TaskStatus.PENDING
                if ctx is not None:
                    ctx.warning(
                        f"Retrying ({updated_job.retries}/{effective_max_retries})"
                    )
            else:
                # No retry: mark as permanently FAILED
                updated_job.status = TaskStatus.FAILED
                if ctx is not None:
                    ctx.error(f"Job failed permanently: {error_msg}")

            try:
                with self._rm_meta_provide(job.info.created_by):
                    self.rm.create_or_update(job.info.resource_id, updated_job)
            except Exception:
                # Primary update failed - fallback to fail() to ensure
                # the job never stays stuck in PROCESSING
                try:
                    self.fail(job.info.resource_id, error_msg)
                except Exception:
                    pass  # Best effort - storage completely unavailable
                return

            # If not retrying, also call fail() to ensure consistent state
            if not should_retry:
                try:
                    self.fail(job.info.resource_id, error_msg)
                except Exception:
                    pass  # Already saved FAILED status above

    def start_consume(self) -> None:
        """Start consuming jobs from the queue."""
        import time

        # Reset stop signals so a previously-stopped queue can be restarted.
        self._recovery_stop_event.clear()

        # Recover any jobs left in PROCESSING from a previous crash
        self.recover_stale_jobs(heartbeat_timeout_seconds=self._heartbeat_interval * 3)

        # Start background periodic recovery for ongoing stale job detection
        self._start_periodic_recovery()

        self._running = True
        while self._running:
            # Check for periodic jobs ready to run
            self._check_periodic_jobs()

            job = self.pop()
            if job:
                try:
                    self._execute_job(job)
                except Exception:
                    # Safety net: _execute_job should handle all errors internally,
                    # but if something unexpected escapes, ensure the consumer
                    # loop continues running and the job is marked as FAILED.
                    try:
                        self.fail(
                            job.info.resource_id,
                            "Unexpected error during job execution",
                        )
                    except Exception:
                        pass  # Best effort
            else:
                time.sleep(0.1)

    def stop_consuming(self):
        """Stop the consumption loop."""
        self._running = False
        super().stop_consuming()


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
