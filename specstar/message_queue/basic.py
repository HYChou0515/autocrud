import datetime as dt
import inspect
import threading
import warnings
from abc import abstractmethod
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from specstar.query_types import (
    DataSearchCondition,
    DataSearchOperator,
    ResourceMetaSearchQuery,
)
from specstar.types import (
    IMessageQueue,
    IResourceManager,
    Job,
    Resource,
    TaskStatus,
)

if TYPE_CHECKING:
    from specstar.message_queue.context import JobContext

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
    provided by SpecStar's ResourceManager.
    """

    def __init__(self, do: Callable[[Resource[Job[T]]], None]):
        self._rm: IResourceManager[Job[T]] | None = None
        self._do = do
        self._handler_wants_ctx = self._check_handler_wants_context(do)
        self._heartbeat_interval: float = 5.0
        self._recovery_interval: float = 60.0
        self._recovery_stop_event: threading.Event = threading.Event()
        self._recovery_thread: threading.Thread | None = None
        # When a job is held back because a same-``partition_key`` peer is
        # already PROCESSING (#384), it is re-scheduled after this many
        # seconds rather than run concurrently. A blocked job is *not*
        # counted as a retry. Public attribute — set it after construction
        # to tune defer cadence.
        self.partition_retry_delay_seconds: float = 1.0

    # ------------------------------------------------------------------
    # Handler introspection
    # ------------------------------------------------------------------

    @staticmethod
    def _check_handler_wants_context(fn: Callable) -> bool:
        """Return ``True`` if *fn* declares a ``job_context`` parameter.

        The check is performed once at init time so there is zero
        per-invocation overhead.
        """
        try:
            sig = inspect.signature(fn)
            return "job_context" in sig.parameters
        except (ValueError, TypeError):
            return False

    def _invoke_handler(
        self,
        resource: Resource[Job[T]],
        ctx: "JobContext | None" = None,
    ):
        """Call the user handler, optionally passing *ctx*.

        If the handler's signature contains a ``job_context`` parameter,
        it is passed as a keyword argument.  Otherwise the handler is
        called with just the ``resource`` — fully backward-compatible.

        When the handler requests ``job_context`` but *ctx* is ``None``
        (e.g. no blob store configured), a fallback :class:`JobContext`
        is created on the fly.  Its API is fully functional (logging,
        artifacts, etc.) but logs will **not** be persisted.  A
        :func:`warnings.warn` is emitted so the operator notices.

        Args:
            resource: The job resource to process.
            ctx: The :class:`JobContext` for this execution (may be ``None``).

        Returns:
            Whatever the user handler returns (used to detect ``False``
            for periodic-job stop requests).
        """
        if self._handler_wants_ctx:
            if ctx is None:
                from specstar.message_queue.context import JobContext

                warnings.warn(
                    "Handler requests job_context but no JobContext was "
                    "provided (blob store may not be configured). "
                    "A fallback context is supplied; logs will not be "
                    "persisted to blob storage.",
                    UserWarning,
                    stacklevel=2,
                )
                ctx = JobContext(resource)
            return self._do(resource, job_context=ctx)  # ty:ignore[unknown-argument]
        return self._do(resource)

    @property
    def rm(self) -> IResourceManager[Job[T]]:
        """The associated ResourceManager."""
        if self._rm is None:
            raise RuntimeError(
                "ResourceManager has not been set. "
                "Call set_resource_manager() before using the message queue."
            )
        return self._rm

    def _rm_using(self, user: str):
        """Helper to provide operation context for ResourceManager operations."""
        return self.rm.using(
            now=self.rm.now_or_unset or dt.datetime.now(),
            user=self.rm.user_or_unset or user,
        )

    # Keep deprecated alias for backward compatibility
    def _rm_meta_provide(self, user: str):
        """Deprecated: use ``_rm_using`` instead."""
        return self._rm_using(user)

    @staticmethod
    def _initial_heartbeat() -> dt.datetime:
        """Proof-of-life stamped on a job at claim time (#404).

        Claiming a job *is* its first heartbeat: a job just moved to PROCESSING
        has, by definition, just shown life. Without this, ``last_heartbeat_at``
        stays ``None`` until the HeartbeatThread's first tick — one
        ``_heartbeat_interval`` away — and :meth:`recover_stale_jobs` treats that
        ``None`` window as a dead worker, falsely recovering a live,
        freshly-claimed job. Wall-clock UTC, consistent with HeartbeatThread.
        """
        return dt.datetime.now(dt.timezone.utc)

    # ------------------------------------------------------------------
    # Enqueue + partition serialization (#384)
    # ------------------------------------------------------------------

    def enqueue(
        self,
        payload: T,
        *,
        partition_key: str | None = None,
        idempotency_key: str | None = None,
    ) -> Resource[Job[T]]:
        """Create-and-enqueue in one step, honoring optional dedup +
        per-key serialization tags.

        Why this exists alongside ``put()``:
            ``put(resource_id)`` is the low-level "already-created" entry
            point. ``enqueue()`` is the user-facing path that knows about
            the dedup/serialization semantics — it owns the "is this a
            retry of an enqueue I already processed?" check because that
            check must happen *before* the new resource is created
            (otherwise dedup is a race).

        Defined here on :class:`BasicMessageQueue` so every backend
        (Simple, RabbitMQ, Celery) exposes the same contract — see #384.
        The ``partition_key`` *enforcement* is per-backend (it happens at
        claim time); this method only records the tags on the job.

        Args:
            payload: The job payload.
            partition_key: When set, no two jobs with this same key run
                concurrently. ``None`` = no serialization. Enforcement is
                strict on :class:`SimpleMessageQueue` (single consumer) and
                best-effort on multi-worker backends.
            idempotency_key: When set, a prior enqueue with this key
                returns the *original* job — including after completion —
                so caller retries are exactly-once. Re-using a key with a
                different payload raises :class:`ValueError` (programming
                error, not a benign retry).

        Returns:
            The job resource (existing one on dedup, fresh one otherwise).
        """
        if idempotency_key is not None:
            existing = self._find_by_idempotency_key(idempotency_key)
            if existing is not None:
                if existing.data.payload != payload:
                    raise ValueError(
                        f"idempotency_key {idempotency_key!r} was previously "
                        "used with a different payload — refusing to dedup "
                        "across mismatched requests. Use a fresh key or "
                        "send the original payload."
                    )
                return existing

        job: Job[T] = Job(
            payload=payload,
            partition_key=partition_key,
            idempotency_key=idempotency_key,
        )
        info = self.rm.create(job)  # ty:ignore[invalid-argument-type]
        return self.put(info.resource_id)

    def _find_by_idempotency_key(self, idempotency_key: str) -> Resource[Job[T]] | None:
        """Look up an existing job by ``idempotency_key``.

        Returns ``None`` if no prior enqueue used this key. Returns the
        resource regardless of its current status — the contract is "same
        key → same job, forever", including after completion (otherwise a
        late retry would re-do the work).

        Relies on ``idempotency_key`` being a registered indexed field so
        the equality search hits an index rather than degrading on SQL
        backends; ``crud`` auto-registers it for the job model (#384).
        """
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="idempotency_key",
                    operator=DataSearchOperator.equals,
                    value=idempotency_key,
                )
            ],
            limit=1,
        )
        metas = self.rm.search_resources(query)
        for meta in metas:
            try:
                return self.rm.get(meta.resource_id)
            except Exception:
                return None
        return None

    def _busy_partition_keys(self) -> set[str]:
        """Return the set of ``partition_key`` values currently in flight
        (any job with status PROCESSING).

        Walks the PROCESSING set rather than maintaining a separate index
        so the source of truth stays the job records themselves — there's
        no second structure to keep consistent across crashes / recovery.
        """
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="status",
                    operator=DataSearchOperator.equals,
                    value=TaskStatus.PROCESSING,
                )
            ],
        )
        busy: set[str] = set()
        for meta in self.rm.search_resources(query):
            try:
                pk = self.rm.get(meta.resource_id).data.partition_key
            except Exception:
                continue
            if pk is not None:
                busy.add(pk)
        return busy

    def _is_partition_busy(self, partition_key: str) -> bool:
        """Best-effort check: is a peer in ``partition_key`` already PROCESSING?

        Used by the multi-worker backends (RabbitMQ, Celery) at claim time
        to decide whether to defer a job (#384). This is *not* atomic — two
        workers receiving same-partition jobs simultaneously can both see
        ``False`` and proceed, leaving a brief overlap window. For strict
        serialization use a single consumer (:class:`SimpleMessageQueue`).
        """
        return partition_key in self._busy_partition_keys()

    # ------------------------------------------------------------------
    # Log helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _log_key(resource_id: str) -> str:
        """Return the blob-store key for a job's execution log.

        Args:
            resource_id: The job resource ID.

        Returns:
            A key string of the form ``__job_log__/{resource_id}``.
        """
        return f"__job_log__/{resource_id}"

    @property
    def _blob_store(self):
        """Return the blob store from the associated ResourceManager, or ``None``."""
        return getattr(self.rm, "blob_store", None)

    def get_logs(self, resource_id: str) -> str | None:
        """Retrieve the execution log text for a job.

        Args:
            resource_id: The job's resource ID.

        Returns:
            The log text as a string, or ``None`` if no logs exist.
        """
        bs = self._blob_store
        if bs is None:
            return None
        key = self._log_key(resource_id)
        try:
            blob = bs.get(key)
            return blob.data.decode("utf-8") if blob.data else None
        except FileNotFoundError:
            return None

    def complete(
        self,
        resource_id: str,
        result: str | None = None,
        *,
        _artifact: object | None = None,
    ) -> Resource[Job[T]]:
        """Mark a job as completed.

        When *_artifact* is provided it is copied onto the freshly
        fetched ``Job`` before persisting, so that handler-produced
        artifacts survive the round-trip through storage.

        Args:
            resource_id: The ID of the job resource.
            result: Optional result string.
            _artifact: If not ``None``, set on the job before saving.
        """
        resource = self.rm.get(resource_id)
        job = resource.data
        job.status = TaskStatus.COMPLETED
        job.errmsg = result
        if _artifact is not None:
            job.artifact = _artifact  # ty:ignore[invalid-assignment]

        with self._rm_using(resource.info.created_by):
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

        with self._rm_using(resource.info.created_by):
            self.rm.create_or_update(resource_id, job)
        resource.data = job
        return resource

    def recover_stale_jobs(self, heartbeat_timeout_seconds: float) -> list[str]:
        """Recover jobs stuck in PROCESSING status.

        Scans for all jobs with PROCESSING status and determines whether they
        should be marked as FAILED based on heartbeat freshness.

        Args:
            heartbeat_timeout_seconds: Only recover jobs whose
                ``last_heartbeat_at`` is older than this many seconds (or is
                ``None``).  A value of 0 means recover ALL PROCESSING jobs
                regardless of heartbeat (use with caution in multi-worker
                setups).

        Returns:
            List of resource IDs that were recovered.
        """
        recovered: list[str] = []
        query = ResourceMetaSearchQuery(
            conditions=[
                DataSearchCondition(
                    field_path="status",
                    operator=DataSearchOperator.equals,
                    value=TaskStatus.PROCESSING,
                )
            ],
        )
        metas = self.rm.search_resources(query)
        now = dt.datetime.now(dt.timezone.utc)

        for meta in metas:
            try:
                resource = self.rm.get(meta.resource_id)
                job = resource.data

                # When heartbeat_timeout_seconds > 0, skip jobs with a recent
                # heartbeat — they are still being actively processed.
                if heartbeat_timeout_seconds > 0:
                    hb = job.last_heartbeat_at
                    if hb is not None:
                        elapsed = (now - hb).total_seconds()
                        if elapsed < heartbeat_timeout_seconds:
                            continue  # Still alive

                job.status = TaskStatus.FAILED
                job.errmsg = (
                    "Recovered stale job: worker was likely killed "
                    "while processing this job."
                )
                with self._rm_using(resource.info.created_by):
                    self.rm.create_or_update(meta.resource_id, job)
                recovered.append(meta.resource_id)
            except Exception:
                pass  # Best effort
        return recovered

    def _start_periodic_recovery(self) -> None:
        """Start a background thread that periodically calls ``recover_stale_jobs``.

        The thread uses ``_heartbeat_interval * 3`` as the heartbeat timeout so
        that only truly stale jobs (no heartbeat for 3 intervals) are recovered,
        leaving active jobs on other workers untouched.

        The thread runs every ``_recovery_interval`` seconds (default 60 s) and
        is a daemon so it won't block process shutdown.

        If ``_stop_periodic_recovery`` has already been called (i.e. the stop
        event is set), this method is a no-op to avoid a race between
        ``stop_consuming`` and ``start_consume`` running on different threads.
        """
        # If stop was already requested, don't (re-)start the recovery thread.
        if self._recovery_stop_event.is_set():
            return

        def _loop() -> None:
            while not self._recovery_stop_event.is_set():
                self._recovery_stop_event.wait(self._recovery_interval)
                if self._recovery_stop_event.is_set():
                    break
                try:
                    self.recover_stale_jobs(
                        heartbeat_timeout_seconds=self._heartbeat_interval * 3,
                    )
                except Exception:
                    pass  # Best effort

        self._recovery_thread = threading.Thread(
            target=_loop,
            name="stale-job-recovery",
            daemon=True,
        )
        self._recovery_thread.start()

    def _stop_periodic_recovery(self) -> None:
        """Signal the periodic recovery thread to stop and wait for it."""
        self._recovery_stop_event.set()
        if self._recovery_thread is not None:
            self._recovery_thread.join(timeout=max(self._recovery_interval * 2, 2.0))
            self._recovery_thread = None

    def stop_consuming(self) -> None:
        """Stop consuming jobs from the queue."""
        self._stop_periodic_recovery()


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
            with self._rm_using(completed_resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

            # Schedule next run
            self._schedule_delayed_job(resource_id, job.periodic_interval_seconds)
        else:
            # Reached max runs, just update the periodic_runs count
            with self._rm_using(completed_resource.info.created_by):
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
        with self._rm_using(created_by):
            self.rm.create_or_update(resource_id, job_data)

        # Schedule delayed retry
        self._schedule_delayed_job(resource_id, delay_seconds)
