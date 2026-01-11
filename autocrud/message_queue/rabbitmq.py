from autocrud.message_queue.basic import BasicMessageQueue
from autocrud.types import Job, Resource, TaskStatus, IResourceManager
from autocrud.util.naming import NameConverter, NamingFormat
from typing import Callable, Generic, TypeVar


import pika


T = TypeVar("T")


class RabbitMQMessageQueue(BasicMessageQueue[T], Generic[T]):
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
        self.amqp_url = amqp_url
        self.queue_prefix = queue_prefix
        self.queue_name: str | None = None
        self.retry_queue_name: str | None = None
        self.dead_queue_name: str | None = None
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self._connection = None
        self._channel = None

    def set_resource_manager(self, resource_manager: IResourceManager[Job[T]]) -> None:
        """Set the resource manager and configure queue names based on resource type."""
        super().set_resource_manager(resource_manager)

        # Get resource name and convert to snake_case
        resource_name = resource_manager.resource_name
        snake_name = NameConverter(resource_name).to(NamingFormat.SNAKE)

        # Set queue names with prefix
        self.queue_name = f"{self.queue_prefix}{snake_name}"
        self.retry_queue_name = f"{self.queue_name}:retry"
        self.dead_queue_name = f"{self.queue_name}:dead"

        # Now we can establish connection and declare queues
        self._ensure_connection()

    def _ensure_connection(self):
        """Ensure that the AMQP connection and channel are open."""
        if self.queue_name is None:
            raise RuntimeError(
                "Queue names not configured. Call set_resource_manager() first."
            )

        if self._connection is None or self._connection.is_closed:
            params = pika.URLParameters(self.amqp_url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()

            # Declare main queue
            self._channel.queue_declare(queue=self.queue_name, durable=True)

            # Declare dead letter queue (no automatic retry)
            self._channel.queue_declare(queue=self.dead_queue_name, durable=True)

            # Declare retry queue with TTL and dead letter exchange
            # After TTL expires, messages are routed back to main queue
            self._channel.queue_declare(
                queue=self.retry_queue_name,
                durable=True,
                arguments={
                    "x-message-ttl": self.retry_delay_seconds
                    * 1000,  # Convert to milliseconds
                    "x-dead-letter-exchange": "",  # Default exchange
                    "x-dead-letter-routing-key": self.queue_name,  # Route back to main queue
                },
            )

    def put(self, payload: T) -> Resource[Job[T]]:
        """
        Enqueue a new job via RabbitMQ.
        """
        # 1. Create Resource in Abstract Store (Pending)
        job = Job(payload=payload)
        info = self.rm.create(job)
        resource_id = info.resource_id

        # 2. Publish Resource ID to RabbitMQ
        self._ensure_connection()
        self._channel.basic_publish(  # type: ignore
            exchange="",
            routing_key=self.queue_name,
            body=resource_id.encode("utf-8"),
            properties=pika.BasicProperties(delivery_mode=pika.DeliveryMode.Persistent),
        )

        return self.rm.get(resource_id)

    def pop(self) -> Resource[Job[T]] | None:
        """
        Dequeue the next pending job from RabbitMQ and mark it as processing.
        """
        self._ensure_connection()
        # Non-blocking get
        method_frame, header_frame, body = self._channel.basic_get(
            queue=self.queue_name
        )  # type: ignore

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
                self._channel.basic_ack(method_frame.delivery_tag)  # type: ignore

                resource.data = updated_job
                return resource
            except Exception:
                # If resource not found or update fails, Nack with requeue
                # to allow retry or distinct fail handling
                self._channel.basic_nack(method_frame.delivery_tag, requeue=True)  # type: ignore
                return None

        return None

    def _send_to_retry_or_dead(
        self, ch, resource_id: str, retry_count: int, error_message: str
    ) -> None:
        """
        Send a failed message to retry queue or dead letter queue based on retry count.

        Args:
            ch: RabbitMQ channel
            resource_id: The resource identifier
            retry_count: Current retry count
            error_message: Error message from the failure
        """
        if retry_count < self.max_retries:
            # Send to retry queue (will auto-route back to main queue after TTL)
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
                    "x-last-error": error_message[:500],  # Limit error message length
                },
            ),
        )

    def start_consume(self) -> None:
        """
        Start consuming jobs from the queue with the configured callback.

        This method blocks and processes jobs as they arrive. Failed jobs are
        automatically retried based on the configured retry policy. Jobs exceeding
        max retries are sent to the dead letter queue.
        """
        self._ensure_connection()

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
                try:
                    self._do(resource)
                    # 3. Complete (Update RM) & Ack (RabbitMQ)
                    self.complete(resource_id)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    # 4. Callback failed - update Job with error and retry info
                    error_msg = str(e)

                    # Update Job with error message and retry count
                    job.status = TaskStatus.FAILED
                    job.result = error_msg  # Store error message in result field
                    job.retries = retry_count + 1  # Increment retry count
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(resource_id, job)

                    # Send to retry or dead letter queue
                    self._send_to_retry_or_dead(ch, resource_id, retry_count, error_msg)

                    # Ack the original message (it's now in retry/dead queue)
                    ch.basic_ack(delivery_tag=method.delivery_tag)

            except Exception as e:
                # Resource fetch failure, RM update failure, or critical error
                error_msg = f"Critical error: {str(e)}"

                # Try to update Job if we have it
                try:
                    resource = self.rm.get(resource_id)
                    job = resource.data
                    job.status = TaskStatus.FAILED
                    job.result = error_msg
                    job.retries = retry_count + 1
                    with self._rm_meta_provide(resource.info.created_by):
                        self.rm.create_or_update(resource_id, job)
                except Exception:
                    # If we can't update, just log and continue
                    pass

                # Send to retry or dead letter queue
                self._send_to_retry_or_dead(ch, resource_id, retry_count, error_msg)
                ch.basic_ack(delivery_tag=method.delivery_tag)

        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(queue=self.queue_name, on_message_callback=callback)
        self._channel.start_consuming()

    def stop_consuming(self):
        """Stop the consumption loop."""

        def stop():
            if self._channel and self._channel.is_open:
                self._channel.stop_consuming()

        if self._connection and self._connection.is_open:
            self._connection.add_callback_threadsafe(stop)


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

    def build(self, do: Callable[[Resource[Job[T]]], None]) -> RabbitMQMessageQueue[T]:
        """Build a RabbitMQMessageQueue instance with a job handler.

        Args:
            do: Callback function to process each job.

        Returns:
            A RabbitMQMessageQueue instance. The resource manager should be
            injected later via set_resource_manager().
        """
        return RabbitMQMessageQueue(
            do=do,
            amqp_url=self.amqp_url,
            queue_prefix=self.queue_prefix,
            max_retries=self.max_retries,
            retry_delay_seconds=self.retry_delay_seconds,
        )
