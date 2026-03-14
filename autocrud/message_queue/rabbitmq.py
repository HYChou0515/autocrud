from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from autocrud.message_queue.basic import DelayableMessageQueue, DelayRetry, NoRetry
from autocrud.types import Job, Resource, RevisionStatus, TaskStatus
from autocrud.util.naming import NameConverter, NamingFormat

try:
    import pika
except ImportError:
    pika = None  # type: ignore

if TYPE_CHECKING:
    from pika.adapters.blocking_connection import BlockingChannel
    from pika.spec import Basic, BasicProperties

    from autocrud.types import IResourceManager

T = TypeVar("T")


class RabbitMQMessageQueue(DelayableMessageQueue[T], Generic[T]):
    """
    AMQP-based Message Queue implementation using RabbitMQ (via pika).

    This implementation uses RabbitMQ for the queuing mechanism (ordering, distribution)
    and AutoCRUD ResourceManager for payload storage and status persistence.

    Features:
    - Automatic retry on failure with configurable delay
    - Dead letter queue for messages exceeding max retries
    - Configurable retry delay and max retry count

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
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        queue_prefix: str = "autocrud:",
        max_retries: int = 3,
        retry_delay_seconds: int = 10,
        amqp_heartbeat_seconds: int = 600,
    ):
        if pika is None:
            raise ImportError(
                "The 'pika' package is required for RabbitMQMessageQueue. Install it via 'pip install pika'"
            )

        super().__init__(do)
        self._rm = resource_manager
        self.amqp_url = amqp_url
        self.queue_prefix = queue_prefix
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.amqp_heartbeat_seconds = amqp_heartbeat_seconds

        # Track worker threads so callers can wait for in-flight jobs.
        self._worker_threads: list[threading.Thread] = []

        # Get resource name and convert to snake_case
        resource_name = resource_manager.resource_name
        snake_name = NameConverter(resource_name).to(NamingFormat.SNAKE)

        # Set queue names with prefix
        self.queue_name = f"{self.queue_prefix}{snake_name}"
        self.retry_queue_name = f"{self.queue_name}:retry"
        self.dead_queue_name = f"{self.queue_name}:dead"

        # Declare queues once during initialization
        self._declare_queues()

    @contextmanager
    def _get_connection(self):
        """Context manager for RabbitMQ connection and channel.

        Creates a new connection for each operation to ensure thread safety.
        Automatically closes the connection when exiting the context.

        The AMQP ``heartbeat`` is explicitly set on connection parameters
        so that long-running jobs do not cause RabbitMQ to close the
        connection due to missed heartbeats.  The value is taken from
        :attr:`amqp_heartbeat_seconds` (default 600).
        """
        params = pika.URLParameters(self.amqp_url)
        params.heartbeat = self.amqp_heartbeat_seconds
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        try:
            yield connection, channel
        finally:
            if connection.is_open:
                connection.close()

    def _declare_queues(self):
        """Declare all required queues during initialization."""
        with self._get_connection() as (_, channel):
            # Declare main queue
            channel.queue_declare(queue=self.queue_name, durable=True)

            # Declare dead letter queue (no automatic retry)
            channel.queue_declare(queue=self.dead_queue_name, durable=True)

            # Declare retry queue with TTL and dead letter exchange
            # After TTL expires, messages are routed back to main queue
            channel.queue_declare(
                queue=self.retry_queue_name,
                durable=True,
                arguments={
                    "x-message-ttl": self.retry_delay_seconds
                    * 1000,  # Convert to milliseconds
                    "x-dead-letter-exchange": "",  # Default exchange
                    "x-dead-letter-routing-key": self.queue_name,  # Route back to main queue
                },
            )

            # Note: Periodic delay queue is created dynamically per-job with specific TTL

    def put(self, resource_id: str) -> Resource[Job[T]]:
        """
        Enqueue a job that has already been created via RabbitMQ.

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
            # Use periodic delay queue mechanism for initial delay
            self._schedule_delayed_job(resource_id, job.periodic_initial_delay_seconds)
        else:
            # Publish Resource ID to RabbitMQ immediately
            with self._get_connection() as (_, channel):
                channel.basic_publish(
                    exchange="",
                    routing_key=self.queue_name,
                    body=resource_id.encode("utf-8"),
                    properties=pika.BasicProperties(
                        delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE
                    ),
                )

        return resource

    def pop(self) -> Resource[Job[T]] | None:
        """
        Dequeue the next pending job from RabbitMQ and mark it as processing.
        """
        with self._get_connection() as (_, channel):
            # Non-blocking get
            method_frame, header_frame, body = channel.basic_get(queue=self.queue_name)

            if method_frame:
                resource_id = body.decode("utf-8")
                try:
                    # 1. Fetch resource
                    resource = self.rm.get(resource_id)

                    # 2. Update status to PROCESSING
                    # Note: We update RM first. If update fails, we don't Ack.
                    # Use draft status so HeartbeatThread can use modify()
                    updated_job = resource.data
                    updated_job.status = TaskStatus.PROCESSING
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(
                            resource_id,
                            updated_job,
                            status=RevisionStatus.draft,
                        )

                    # 3. Ack message
                    channel.basic_ack(method_frame.delivery_tag)

                    resource.data = updated_job
                    return resource
                except Exception:
                    # If resource not found or update fails, Nack with requeue
                    # to allow retry or distinct fail handling
                    channel.basic_nack(method_frame.delivery_tag, requeue=True)
                    return None

        return None

    def _send_to_retry_or_dead(
        self,
        ch: BlockingChannel,
        resource_id: str,
        retry_count: int,
        err: Exception,
        *,
        job_max_retries: int | None = None,
    ) -> None:
        """
        Send a failed message to retry queue or dead letter queue based on retry count.

        Args:
            ch: RabbitMQ channel
            resource_id: The resource identifier
            retry_count: Current retry count
            err: Exception from the failure
            job_max_retries: Per-job max retry override. When ``None``,
                the queue-level ``self.max_retries`` is used.
        """
        error_msg = str(err)
        effective_max_retries = (
            job_max_retries if job_max_retries is not None else self.max_retries
        )
        if not isinstance(err, NoRetry) and retry_count < effective_max_retries:
            target_queue = self.retry_queue_name
            new_retry_count = retry_count + 1
        else:
            # Max retries exceeded, send to dead letter queue
            target_queue = self.dead_queue_name
            new_retry_count = retry_count

        ch.basic_publish(
            exchange="",
            routing_key=target_queue,
            body=resource_id.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
                headers={
                    "x-retry-count": new_retry_count,
                    "x-last-error": error_msg[:500],  # Limit error message length
                },
            ),
        )

    def _enqueue_periodic_job(
        self, ch: BlockingChannel, resource_id: str, interval_seconds: int
    ) -> None:
        """
        Enqueue a periodic job to a delay queue for re-execution.

        Uses a delay queue with TTL equal to the periodic interval.
        After TTL expires, the job is automatically routed back to the main queue.

        Args:
            ch: RabbitMQ channel
            resource_id: The resource identifier
            interval_seconds: Delay before re-execution in seconds
        """
        # Create a unique delay queue for this interval if it doesn't exist
        # This allows multiple jobs with different intervals
        delay_queue_name = f"{self.queue_name}:periodic:{interval_seconds}s"

        # Declare delay queue with TTL and dead letter routing
        ch.queue_declare(
            queue=delay_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": interval_seconds * 1000,  # Convert to milliseconds
                "x-dead-letter-exchange": "",  # Default exchange
                "x-dead-letter-routing-key": self.queue_name,  # Route back to main queue
            },
        )

        # Publish to delay queue
        ch.basic_publish(
            exchange="",
            routing_key=delay_queue_name,
            body=resource_id.encode("utf-8"),
            properties=pika.BasicProperties(
                delivery_mode=pika.spec.PERSISTENT_DELIVERY_MODE,
            ),
        )

    def _schedule_delayed_job(self, resource_id: str, delay_seconds: int) -> None:
        """
        Implementation of abstract method from DelayableMessageQueue.

        Schedules a job for delayed execution using RabbitMQ delay queue.

        Args:
            resource_id: The ID of the job resource to schedule
            delay_seconds: Number of seconds to delay before execution
        """
        with self._get_connection() as (_, channel):
            self._enqueue_periodic_job(channel, resource_id, delay_seconds)

    def _execute_job(
        self,
        ch: BlockingChannel,
        method: Basic.Deliver,
        resource: Resource[Job[T]],
        retry_count: int,
    ) -> None:
        """
        Execute a job on a **worker thread** and handle success,
        :class:`DelayRetry`, or failure.

        The callback returns immediately so that the pika I/O thread can
        continue to service AMQP heartbeats.  ACK / NACK is delivered
        back to the I/O thread via
        ``connection.add_callback_threadsafe``.

        A :class:`HeartbeatThread` keeps ``job.last_heartbeat_at``
        up-to-date so that :meth:`recover_stale_jobs` can distinguish
        live workers from dead ones (consistent with
        :class:`SimpleMessageQueue`).

        A :class:`LogFlushThread` periodically persists execution logs
        when a blob store is configured.

        Args:
            ch: RabbitMQ channel
            method: RabbitMQ method frame
            resource: The job resource to execute
            retry_count: Current retry count from message headers
        """
        connection = self._consuming_connection

        def _worker() -> None:
            from autocrud.message_queue.context import JobContext
            from autocrud.message_queue.heartbeat import HeartbeatThread
            from autocrud.message_queue.log_flush import LogFlushThread

            resource_id = resource.info.resource_id
            job = resource.data

            ctx = JobContext(resource)
            ctx.info("Job started")

            # -- Application-level heartbeat (same as SimpleMessageQueue) --
            hb = HeartbeatThread(
                mq=self,
                resource_id=resource_id,
                interval_seconds=self._heartbeat_interval,
            )
            hb.start()

            blob_store = self._blob_store
            log_key = self._log_key(resource_id)
            lf: LogFlushThread | None = None
            if blob_store is not None:
                lf = LogFlushThread(ctx=ctx, blob_store=blob_store, key=log_key)
                lf.start()

            try:
                result = self._invoke_handler(resource, ctx)
                # Check if callback explicitly requested to stop periodic execution
                user_requested_stop = result is False

                ctx.info("Job completed")

                # Complete (Update RM)
                completed_resource = self.complete(
                    resource_id, _artifact=resource.data.artifact
                )

                # ACK via I/O thread
                def _ack():
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                connection.add_callback_threadsafe(_ack)

                # Handle periodic job using parent class method
                self._handle_periodic_job(
                    resource_id, completed_resource, user_requested_stop
                )

            except DelayRetry as e:
                ctx.info(f"Job delayed retry: {e.delay_seconds}s")

                def _ack_delay():
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                connection.add_callback_threadsafe(_ack_delay)
                self._handle_delay_retry(
                    resource_id, e.delay_seconds, resource.info.created_by
                )

            except Exception as e:
                # Callback failed - update Job with error and retry info
                error_msg = str(e)
                ctx.error(f"Job error: {error_msg}")

                # Capture exception before it's deleted at except-block exit
                exc = e
                job_max = job.max_retries

                # Re-fetch from storage to avoid serialization issues
                try:
                    job = self.rm.get(resource_id).data
                    job_max = job.max_retries
                except Exception:
                    pass  # keep in-memory version as fallback
                job.status = TaskStatus.FAILED
                job.errmsg = error_msg
                job.retries = retry_count + 1
                try:
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(resource_id, job)
                except Exception:
                    pass  # Best effort

                def _ack_fail():
                    self._send_to_retry_or_dead(
                        ch,
                        resource_id,
                        retry_count,
                        exc,
                        job_max_retries=job_max,
                    )
                    ch.basic_ack(delivery_tag=method.delivery_tag)

                connection.add_callback_threadsafe(_ack_fail)

            except BaseException:
                # Safety net (e.g. KeyboardInterrupt, SystemExit, OOM-adjacent).
                # NACK with requeue so another worker can pick it up.
                def _nack():
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                connection.add_callback_threadsafe(_nack)

            finally:
                hb.stop()
                if lf is not None:
                    lf.stop()

        thread = threading.Thread(
            target=_worker,
            name=f"rmq-worker-{resource.info.resource_id}",
            daemon=True,
        )
        self._worker_threads.append(thread)
        thread.start()

    def start_consume(self) -> None:
        """
        Start consuming jobs from the queue with the configured callback.

        This method blocks and processes jobs as they arrive.  Each job
        is executed on a **dedicated worker thread** so that the pika I/O
        thread stays free to service AMQP heartbeats.

        Failed jobs are automatically retried based on the configured
        retry policy.  Jobs exceeding max retries are sent to the dead
        letter queue.

        Note: This creates a dedicated connection for consuming that
        persists for the lifetime of the consumer.
        """
        # Recover any jobs left in PROCESSING from a previous crash
        self.recover_stale_jobs(heartbeat_timeout_seconds=self._heartbeat_interval * 3)

        # Start background periodic recovery for ongoing stale job detection
        self._start_periodic_recovery()

        # Use context manager to ensure proper cleanup
        with self._get_connection() as (connection, channel):
            # Store references for stop_consuming() and worker threads
            self._consuming_connection = connection
            self._consuming_channel = channel

            def callback(
                ch: BlockingChannel,
                method: Basic.Deliver,
                properties: BasicProperties,
                body: bytes,
            ) -> None:
                resource_id = body.decode("utf-8")

                # Get retry count from message headers
                retry_count = 0
                if properties.headers and "x-retry-count" in properties.headers:
                    retry_count = properties.headers["x-retry-count"]

                try:
                    # 1. Fetch & Update status to PROCESSING
                    # If this fails (e.g. resource deleted), we fall to outer except
                    # Use draft status so HeartbeatThread can use modify()
                    resource = self.rm.get(resource_id)
                    job = resource.data
                    job.status = TaskStatus.PROCESSING
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(
                            resource_id,
                            job,
                            status=RevisionStatus.draft,
                        )
                    resource.data = job

                    # 2. Execute user callback (spawns a worker thread)
                    self._execute_job(ch, method, resource, retry_count)

                except Exception as e:
                    # Resource fetch failure, RM update failure, or critical error
                    # Try to update Job if we have it
                    job_max_retries = None
                    try:
                        resource = self.rm.get(resource_id)
                        job = resource.data
                        job_max_retries = job.max_retries
                        job.status = TaskStatus.FAILED
                        job.errmsg = str(e)
                        job.retries = retry_count + 1
                        with self._rm_meta_provide(resource.info.created_by):
                            self.rm.create_or_update(resource_id, job)
                    except Exception:
                        # If we can't update, just log and continue
                        pass

                    # Send to retry or dead letter queue
                    self._send_to_retry_or_dead(
                        ch,
                        resource_id,
                        retry_count,
                        e,
                        job_max_retries=job_max_retries,
                    )
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=self.queue_name, on_message_callback=callback)

            try:
                channel.start_consuming()
            finally:
                # Wait for any in-flight worker threads to finish and
                # schedule their ACK/NACK callbacks.
                self._join_workers()
                # Flush pending add_callback_threadsafe callbacks that
                # workers scheduled but the event loop did not process
                # before start_consuming() exited.
                try:
                    connection.process_data_events(time_limit=0)
                except Exception:
                    pass

    def _join_workers(self, timeout: float = 30) -> None:
        """Wait for all in-flight worker threads to finish.

        This is called internally during shutdown and can also be used
        by tests to synchronise with asynchronous worker threads.

        Args:
            timeout: Maximum seconds to wait per thread.
        """
        for t in self._worker_threads:
            t.join(timeout=timeout)
        self._worker_threads.clear()

    def stop_consuming(self):
        """Signal the consumption loop to stop.

        This can be called from a different thread.  The actual cleanup
        (joining worker threads, flushing pending callbacks, clearing
        references) happens in :meth:`start_consume`'s ``finally``
        block so that the pika connection stays open long enough for
        all in-flight workers to ACK/NACK.
        """
        super().stop_consuming()
        conn = self._consuming_connection
        if conn is not None and getattr(conn, "is_open", False):

            def _stop():
                ch = self._consuming_channel
                if ch is not None and getattr(ch, "is_open", False):
                    ch.stop_consuming()

            conn.add_callback_threadsafe(_stop)


class RabbitMQMessageQueueFactory:
    """Factory for creating RabbitMQMessageQueue instances."""

    def __init__(
        self,
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        queue_prefix: str = "autocrud:",
        max_retries: int = 3,
        retry_delay_seconds: int = 10,
        amqp_heartbeat_seconds: int = 600,
    ):
        """Initialize the RabbitMQ message queue factory.

        Args:
            amqp_url: AMQP connection URL (default: local RabbitMQ)
            queue_prefix: Prefix for queue names (default: "autocrud:")
            max_retries: Maximum number of retries for failed jobs (default: 3)
            retry_delay_seconds: Delay in seconds before retrying a failed job (default: 10)
            amqp_heartbeat_seconds: AMQP heartbeat interval in seconds
                (default: 600).  Set on every connection so that
                long-running jobs do not trigger a heartbeat timeout.
        """
        self.amqp_url = amqp_url
        self.queue_prefix = queue_prefix
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.amqp_heartbeat_seconds = amqp_heartbeat_seconds

    def build(
        self, do: Callable[[Resource[Job[T]]], None]
    ) -> Callable[["IResourceManager[Job[T]]"], RabbitMQMessageQueue[T]]:
        """Build a RabbitMQMessageQueue factory function.

        Args:
            do: Callback function to process each job.

        Returns:
            A callable that accepts an IResourceManager and returns a RabbitMQMessageQueue instance.
        """

        def create_queue(
            resource_manager: "IResourceManager[Job[T]]",
        ) -> RabbitMQMessageQueue[T]:
            return RabbitMQMessageQueue(
                do=do,
                resource_manager=resource_manager,
                amqp_url=self.amqp_url,
                queue_prefix=self.queue_prefix,
                max_retries=self.max_retries,
                retry_delay_seconds=self.retry_delay_seconds,
                amqp_heartbeat_seconds=self.amqp_heartbeat_seconds,
            )

        return create_queue
