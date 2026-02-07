from contextlib import contextmanager
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

from autocrud.message_queue.basic import DelayableMessageQueue, DelayRetry, NoRetry
from autocrud.types import Job, Resource, TaskStatus
from autocrud.util.naming import NameConverter, NamingFormat

try:
    import pika
except ImportError:
    pika = None  # type: ignore

if TYPE_CHECKING:
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
    """

    def __init__(
        self,
        do: Callable[[Resource[Job[T]]], None],
        resource_manager: "IResourceManager[Job[T]]",
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        queue_prefix: str = "autocrud:",
        max_retries: int = 3,
        retry_delay_seconds: int = 10,
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
        """
        params = pika.URLParameters(self.amqp_url)
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
                        delivery_mode=pika.DeliveryMode.Persistent
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
                    updated_job = resource.data
                    updated_job.status = TaskStatus.PROCESSING
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(resource_id, updated_job)

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
        self, ch, resource_id: str, retry_count: int, err: Exception
    ) -> None:
        """
        Send a failed message to retry queue or dead letter queue based on retry count.

        Args:
            ch: RabbitMQ channel
            resource_id: The resource identifier
            retry_count: Current retry count
            err: Exception from the failure
        """
        error_msg = str(err)
        if not isinstance(err, NoRetry) and retry_count < self.max_retries:
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
                delivery_mode=pika.DeliveryMode.Persistent,
                headers={
                    "x-retry-count": new_retry_count,
                    "x-last-error": error_msg[:500],  # Limit error message length
                },
            ),
        )

    def _enqueue_periodic_job(
        self, ch, resource_id: str, interval_seconds: int
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
                delivery_mode=pika.DeliveryMode.Persistent,
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
        self, ch, method, resource: Resource[Job[T]], retry_count: int
    ) -> None:
        """
        Execute a job and handle success, DelayRetry, or failure.

        Args:
            ch: RabbitMQ channel
            method: RabbitMQ method frame
            resource: The job resource to execute
            retry_count: Current retry count from message headers
        """
        resource_id = resource.info.resource_id
        job = resource.data

        try:
            result = self._do(resource)
            # Check if callback explicitly requested to stop periodic execution
            user_requested_stop = result is False

            # Complete (Update RM) & Ack (RabbitMQ)
            completed_resource = self.complete(resource_id)
            ch.basic_ack(delivery_tag=method.delivery_tag)

            # Handle periodic job using parent class method
            self._handle_periodic_job(
                resource_id, completed_resource, user_requested_stop
            )

        except DelayRetry as e:
            # Handle DelayRetry using parent class method
            ch.basic_ack(delivery_tag=method.delivery_tag)
            self._handle_delay_retry(
                resource_id, e.delay_seconds, resource.info.created_by
            )

        except Exception as e:
            # Callback failed - update Job with error and retry info
            error_msg = str(e)

            # Update Job with error message and retry count
            job.status = TaskStatus.FAILED
            job.errmsg = error_msg
            job.retries = retry_count + 1
            with self._rm_meta_provide(resource.info.created_by):
                self.rm.create_or_update(resource_id, job)

            # Send to retry or dead letter queue
            self._send_to_retry_or_dead(ch, resource_id, retry_count, e)

            # Ack the original message (it's now in retry/dead queue)
            ch.basic_ack(delivery_tag=method.delivery_tag)

    def start_consume(self) -> None:
        """
        Start consuming jobs from the queue with the configured callback.

        This method blocks and processes jobs as they arrive. Failed jobs are
        automatically retried based on the configured retry policy. Jobs exceeding
        max retries are sent to the dead letter queue.

        Note: This creates a dedicated connection for consuming that persists
        for the lifetime of the consumer.
        """
        # Use context manager to ensure proper cleanup
        with self._get_connection() as (connection, channel):
            # Store references for stop_consuming()
            self._consuming_connection = connection
            self._consuming_channel = channel

            def callback(ch, method, properties, body):
                resource_id = body.decode("utf-8")

                # Get retry count from message headers
                retry_count = 0
                if properties.headers and "x-retry-count" in properties.headers:
                    retry_count = properties.headers["x-retry-count"]

                try:
                    # 1. Fetch & Update status to PROCESSING
                    # If this fails (e.g. resource deleted), we fall to outer except
                    resource = self.rm.get(resource_id)
                    job = resource.data
                    job.status = TaskStatus.PROCESSING
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(resource_id, job)
                    resource.data = job

                    # 2. Execute user callback
                    self._execute_job(ch, method, resource, retry_count)

                except Exception as e:
                    # Resource fetch failure, RM update failure, or critical error
                    # Try to update Job if we have it
                    try:
                        resource = self.rm.get(resource_id)
                        job = resource.data
                        job.status = TaskStatus.FAILED
                        job.errmsg = str(e)
                        job.retries = retry_count + 1
                        with self._rm_meta_provide(resource.info.created_by):
                            self.rm.create_or_update(resource_id, job)
                    except Exception:
                        # If we can't update, just log and continue
                        pass

                    # Send to retry or dead letter queue
                    self._send_to_retry_or_dead(ch, resource_id, retry_count, e)
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            channel.basic_qos(prefetch_count=1)
            channel.basic_consume(queue=self.queue_name, on_message_callback=callback)

            try:
                channel.start_consuming()
            finally:
                # Clear references when exiting
                self._consuming_connection = None
                self._consuming_channel = None

    def stop_consuming(self):
        """Stop the consumption loop.

        This can be called from a different thread to gracefully stop consumption.
        """
        if hasattr(self, "_consuming_connection") and self._consuming_connection:
            if self._consuming_connection.is_open:
                # Use thread-safe callback to stop consuming
                def stop():
                    if self._consuming_channel and self._consuming_channel.is_open:
                        self._consuming_channel.stop_consuming()

                self._consuming_connection.add_callback_threadsafe(stop)


class RabbitMQMessageQueueFactory:
    """Factory for creating RabbitMQMessageQueue instances."""

    def __init__(
        self,
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        queue_prefix: str = "autocrud:",
        max_retries: int = 3,
        retry_delay_seconds: int = 10,
    ):
        """Initialize the RabbitMQ message queue factory.

        Args:
            amqp_url: AMQP connection URL (default: local RabbitMQ)
            queue_prefix: Prefix for queue names (default: "autocrud:")
            max_retries: Maximum number of retries for failed jobs (default: 3)
            retry_delay_seconds: Delay in seconds before retrying a failed job (default: 10)
        """
        self.amqp_url = amqp_url
        self.queue_prefix = queue_prefix
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds

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
            )

        return create_queue
