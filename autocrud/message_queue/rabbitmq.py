from autocrud.message_queue.basic import BasicMessageQueue
from autocrud.types import IResourceManager, Job, Resource, TaskStatus
from typing import Callable, Generic, TypeVar


import pika


T = TypeVar("T")


class RabbitMQMessageQueue(BasicMessageQueue[T], Generic[T]):
    """
    AMQP-based Message Queue implementation using RabbitMQ (via pika).

    This implementation uses RabbitMQ for the queuing mechanism (ordering, distribution)
    and AutoCRUD ResourceManager for payload storage and status persistence.
    """

    def __init__(
        self,
        resource_manager: IResourceManager[Job[T]],
        amqp_url: str = "amqp://guest:guest@localhost:5672/",
        queue_name: str = "autocrud_jobs",
    ):
        if pika is None:
            raise ImportError(
                "The 'pika' package is required for RabbitMQMessageQueue. Install it via 'pip install pika'"
            )

        self._rm = resource_manager
        self.amqp_url = amqp_url
        self.queue_name = queue_name
        self._connection = None
        self._channel = None
        self._ensure_connection()

    @property
    def rm(self) -> IResourceManager[Job[T]]:
        """The associated ResourceManager."""
        return self._rm

    def _ensure_connection(self):
        """Ensure that the AMQP connection and channel are open."""
        if self._connection is None or self._connection.is_closed:
            params = pika.URLParameters(self.amqp_url)
            self._connection = pika.BlockingConnection(params)
            self._channel = self._connection.channel()
            self._channel.queue_declare(queue=self.queue_name, durable=True)

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

    def start_consume(self, do: Callable[[Resource[Job[T]]], None]) -> None:
        """
        Start consuming jobs from the queue with the provided callback.

        This method blocks and processes jobs as they arrive.
        """
        self._ensure_connection()

        def callback(ch, method, properties, body):
            resource_id = body.decode("utf-8")
            try:
                # 1. Fetch & Update status to PROCESSING
                # If this fails (e.g. resource deleted), we fall to outer except
                resource = self.rm.get(resource_id)
                job = resource.data
                job.status = TaskStatus.PROCESSING
                self.rm.create_or_update(resource_id, job)
                resource.data = job

                # 2. Execute user callback
                try:
                    do(resource)
                    # 3. Complete (Update RM) & Ack (RabbitMQ)
                    self.complete(resource_id)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as e:
                    # 4. Fail (Update RM) & Nack (RabbitMQ)
                    # If fail() raises (e.g. DB error), we fall to outer except
                    self.fail(resource_id, str(e))
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

            except Exception:
                # Resource fetch failure, RM update failure, or critical error
                # We cannot process this message. Remove from queue (dead letter or drop).
                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

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
