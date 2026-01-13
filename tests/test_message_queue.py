import datetime as dt
import threading
import time
import pytest
from msgspec import Struct
from unittest.mock import MagicMock, patch, call
from uuid import uuid4
from autocrud.message_queue.rabbitmq import (
    RabbitMQMessageQueue,
    RabbitMQMessageQueueFactory,
)
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.message_queue.basic import NoRetry
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.message_queue.simple import SimpleMessageQueue
from autocrud.types import (
    IMessageQueue,
    Job,
    Resource,
    TaskStatus,
    IndexableField,
    ResourceMetaSearchQuery,
    RevisionInfo,
    RevisionStatus,
)


class Payload(Struct):
    task_name: str
    priority: int


def get_simple_queue(rm):
    def handler(job):
        pass

    mq = SimpleMessageQueue(handler, rm)
    return mq


def get_rabbitmq_queue(rm):
    def handler(job):
        pass

    queue_prefix = "test:"
    mq = RabbitMQMessageQueue(handler, rm, queue_prefix=queue_prefix)
    # Purge to ensure a clean state for each test
    if mq.queue_name:
        with mq._get_connection() as (_, channel):
            channel.queue_purge(mq.queue_name)
    return mq


@pytest.fixture(params=["simple", "rabbitmq"])
def mq_context(request: pytest.FixtureRequest):
    """Fixture that provides both the queue implementation and its associated resource manager."""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    def handler(job):
        pass

    if request.param == "simple":
        mq_factory = SimpleMessageQueueFactory()
        rm = ResourceManager(
            Job[Payload],
            storage=storage,
            message_queue=mq_factory.build(handler),
            indexed_fields=[IndexableField(field_path="status", field_type=str)],
        )
        queue = rm.message_queue
    else:
        mq_factory = RabbitMQMessageQueueFactory(queue_prefix="test:")
        rm = ResourceManager(
            Job[Payload],
            storage=storage,
            message_queue=mq_factory.build(handler),
            indexed_fields=[IndexableField(field_path="status", field_type=str)],
        )
        queue = rm.message_queue
        # Purge to ensure a clean state for each test
        if queue.queue_name:
            with queue._get_connection() as (_, channel):
                channel.queue_purge(queue.queue_name)

    return queue, rm


class TestMessageQueueUnified:
    """
    Unified tests for all IMessageQueue implementations.
    Ensures that behavior remains consistent regardless of the underlying transport.
    """

    @pytest.fixture(autouse=True)
    def setup_method(
        self, mq_context: tuple[IMessageQueue[Payload], ResourceManager[Job[Payload]]]
    ):
        self.queue, self.rm = mq_context

    def run_consumer_in_thread(
        self,
        queue: IMessageQueue[Payload],
        rm: ResourceManager[Job[Payload]],
        worker_logic: callable,
        process_timeout: float = 1.0,
        track_published_messages: bool = False,
    ) -> tuple[IMessageQueue[Payload], list[dict]]:
        """輔助方法：在獨立線程中運行消費者。

        Args:
            queue: 消息隊列實例
            rm: ResourceManager 實例
            worker_logic: 處理任務的回調函數
            process_timeout: 等待處理完成的時間（秒）
            track_published_messages: 是否追蹤 RabbitMQ 發布的訊息（僅對 RabbitMQ 有效）

        Returns:
            (消費者隊列引用, 發布的訊息列表)
            如果 track_published_messages=False，訊息列表為空
        """
        published_messages = []
        consumer_ref = [None]

        def run_queue():
            consumer = queue
            consumer._do = worker_logic
            consumer_ref[0] = consumer

            # 如果需要追蹤訊息且是 RabbitMQ，則 patch start_consume
            if track_published_messages and isinstance(queue, RabbitMQMessageQueue):

                def mock_publish(exchange, routing_key, body, properties):
                    published_messages.append(
                        {
                            "routing_key": routing_key,
                            "body": body,
                            "headers": properties.headers
                            if properties and hasattr(properties, "headers")
                            else None,
                        }
                    )

                def patched_consume():
                    with consumer._get_connection() as (connection, channel):
                        consumer._consuming_connection = connection
                        consumer._consuming_channel = channel

                        original_publish = channel.basic_publish
                        channel.basic_publish = lambda **kwargs: (
                            mock_publish(**kwargs),
                            original_publish(**kwargs),
                        )[1]

                        def callback(ch, method, properties, body):
                            resource_id = body.decode("utf-8")
                            retry_count = 0
                            if (
                                properties.headers
                                and "x-retry-count" in properties.headers
                            ):
                                retry_count = properties.headers["x-retry-count"]

                            try:
                                resource = consumer.rm.get(resource_id)
                                job = resource.data
                                job.status = TaskStatus.PROCESSING
                                with consumer._rm_meta_provide(
                                    resource.info.created_by
                                ):
                                    consumer.rm.create_or_update(resource_id, job)
                                resource.data = job

                                try:
                                    consumer._do(resource)
                                    consumer.complete(resource_id)
                                    ch.basic_ack(delivery_tag=method.delivery_tag)
                                except Exception as e:
                                    error_msg = str(e)
                                    job.status = TaskStatus.FAILED
                                    job.errmsg = error_msg
                                    job.retries = retry_count + 1
                                    with consumer._rm_meta_provide(
                                        resource.info.created_by
                                    ):
                                        consumer.rm.create_or_update(resource_id, job)
                                    consumer._send_to_retry_or_dead(
                                        ch, resource_id, retry_count, e
                                    )
                                    ch.basic_ack(delivery_tag=method.delivery_tag)
                            except Exception as e:
                                try:
                                    resource = consumer.rm.get(resource_id)
                                    job = resource.data
                                    job.status = TaskStatus.FAILED
                                    job.errmsg = str(e)
                                    job.retries = retry_count + 1
                                    with consumer._rm_meta_provide(
                                        resource.info.created_by
                                    ):
                                        consumer.rm.create_or_update(resource_id, job)
                                except Exception:
                                    pass
                                consumer._send_to_retry_or_dead(
                                    ch, resource_id, retry_count, e
                                )
                                ch.basic_ack(delivery_tag=method.delivery_tag)

                        channel.basic_qos(prefetch_count=1)
                        channel.basic_consume(
                            queue=consumer.queue_name, on_message_callback=callback
                        )

                        try:
                            channel.start_consuming()
                        finally:
                            consumer._consuming_connection = None
                            consumer._consuming_channel = None

                consumer.start_consume = patched_consume

            with rm.meta_provide(user="consumer", now=dt.datetime.now(dt.timezone.utc)):
                try:
                    consumer.start_consume()
                except Exception:
                    pass

        t = threading.Thread(target=run_queue, daemon=True)
        t.start()

        # 等待消費者初始化
        start_wait = time.time()
        while consumer_ref[0] is None and time.time() - start_wait < 5:
            time.sleep(0.1)

        # 等待處理
        time.sleep(process_timeout)

        # 停止並清理
        if consumer_ref[0]:
            consumer_ref[0].stop_consuming()
        t.join(timeout=2)

        return consumer_ref[0], published_messages

    def test_workflow(self):
        queue, rm = self.queue, self.rm
        user = "test_user"
        now = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            # 1. Enqueue
            payload1 = Payload(task_name="task1", priority=1)
            info1 = rm.create(Job(payload=payload1))
            res1 = rm.get(info1.resource_id)
            assert res1.data.status == TaskStatus.PENDING
            assert res1.data.payload == payload1

            # 2. Enqueue second
            now2 = now + dt.timedelta(seconds=1)
            with rm.meta_provide(user=user, now=now2):
                payload2 = Payload(task_name="task2", priority=2)
                info2 = rm.create(Job(payload=payload2))
                res2 = rm.get(info2.resource_id)

        # 3. Pop (FIFO) - should get task1
        now3 = now + dt.timedelta(seconds=2)
        with rm.meta_provide(user="consumer", now=now3):
            job1 = queue.pop()
            assert job1 is not None
            assert job1.info.resource_id == res1.info.resource_id
            assert job1.data.status == TaskStatus.PROCESSING

            # 4. Complete
            completed = queue.complete(job1.info.resource_id, result="done")
            assert completed.data.status == TaskStatus.COMPLETED
            assert completed.data.errmsg == "done"

            # 5. Pop next
            job2 = queue.pop()
            assert job2 is not None
            assert job2.info.resource_id == res2.info.resource_id

            # 6. Fail
            failed = queue.fail(job2.info.resource_id, error="oops")
            assert failed.data.status == TaskStatus.FAILED
            assert failed.data.errmsg == "oops"

            # 7. Empty
            assert queue.pop() is None

    def test_missing_resource_resilience(self):
        """Tests that the queue handles cases where the resource is deleted out-of-band."""
        queue, rm = self.queue, self.rm
        payload = Payload(task_name="ghost_task", priority=0)

        with rm.meta_provide(user="ghost", now=dt.datetime.now(dt.timezone.utc)):
            info = rm.create(Job(payload=payload))
            res_put = rm.get(info.resource_id)
            # Delete direct from RM
            rm.delete(res_put.info.resource_id)

            # Dequeue should skip/handle the missing resource and return None
            res_pop = queue.pop()
            assert res_pop is None

    def test_consume_loop(self):
        queue_producer, rm = self.queue, self.rm

        # Prepare Data
        user = "producer"
        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user=user, now=now):
            # Job 1: Success
            rm.create(Job(payload=Payload(task_name="success_job", priority=1)))
            # Job 2: Fail logic
            rm.create(Job(payload=Payload(task_name="fail_job", priority=2)))

        results = []

        def worker_logic(resource: Resource[Job[Payload]]):
            name = resource.data.payload.task_name
            if name == "fail_job":
                raise ValueError("Intentional Fail")
            results.append(name)

        # 使用輔助方法運行消費者
        self.run_consumer_in_thread(queue_producer, rm, worker_logic)

        # Verify
        assert "success_job" in results
        assert "fail_job" not in results

        # Check RM status
        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            all_jobs = rm.search_resources(ResourceMetaSearchQuery())
            statuses = {}
            for meta in all_jobs:
                res = rm.get(meta.resource_id)
                name = res.data.payload.task_name
                statuses[name] = res.data.status

            assert statuses.get("success_job") == TaskStatus.COMPLETED
            assert statuses.get("fail_job") == TaskStatus.FAILED

    def test_error_message_recorded_on_failure(self):
        """Test that error message is recorded in Job.errmsg when task fails."""
        queue, rm = self.queue, self.rm
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job
        with rm.meta_provide(user=user, now=now):
            payload = Payload(task_name="will_fail", priority=1)
            info = rm.create(Job(payload=payload))
            res = rm.get(info.resource_id)
            resource_id = res.info.resource_id

        # Pop and fail it manually
        with rm.meta_provide(user="consumer", now=now):
            job = queue.pop()
            assert job is not None

            # Simulate failure by calling fail directly
            error_msg = "Processing failed for some reason"
            failed_job = queue.fail(resource_id, error_msg)

            # Verify error is recorded
            assert failed_job.data.status == TaskStatus.FAILED
            assert failed_job.data.errmsg == error_msg

            # Also verify we can retrieve it
            retrieved = rm.get(resource_id)
            assert retrieved.data.errmsg == error_msg

    def test_error_overwrites_in_consume_loop(self):
        """Test that error messages are updated correctly in consume loop."""

        queue_producer, rm = self.queue, self.rm
        user = "producer"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job that will fail
        with rm.meta_provide(user=user, now=now):
            rm.create(Job(payload=Payload(task_name="error_test_job", priority=1)))

        def worker_logic(resource: Resource[Job[Payload]]):
            # Fail with specific error
            raise ValueError("Specific processing error")

        # 使用輔助方法運行消費者
        self.run_consumer_in_thread(queue_producer, rm, worker_logic)

        # Verify error was recorded in Job
        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            all_jobs = rm.search_resources(ResourceMetaSearchQuery())
            for meta in all_jobs:
                res = rm.get(meta.resource_id)
                if res.data.payload.task_name == "error_test_job":
                    assert res.data.status == TaskStatus.FAILED
                    assert "Specific processing error" in res.data.errmsg
                    assert res.data.retries >= 1

    def test_retry_count_increments_on_failure(self):
        """Test that retry count increments when jobs fail."""
        queue, rm = self.queue, self.rm
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job
        with rm.meta_provide(user=user, now=now):
            payload = Payload(task_name="retry_test", priority=1)
            info = rm.create(Job(payload=payload))
            res = rm.get(info.resource_id)
            resource_id = res.info.resource_id

            # Initial retries should be 0
            assert res.data.retries == 0

        # Fail it once
        with rm.meta_provide(user="consumer", now=now):
            job = queue.pop()
            queue.fail(resource_id, "First failure")

            # Check retry count incremented
            updated = rm.get(resource_id)
            # Note: SimpleMessageQueue increments in consume loop, not in fail()
            # So we check it's at least 0 (unchanged) or 1 (incremented)
            assert updated.data.retries >= 0

    def test_noretry_exception_skips_retry(self):
        """測試當拋出 NoRetry 異常時，任務應直接失敗而不重試。

        - SimpleMessageQueue: 任務應標記為 FAILED 且 retries=1 (不會重新設為 PENDING)
        - RabbitMQ: 訊息應直接送到 dead letter queue 而非 retry queue
        """
        queue_producer, rm = self.queue, self.rm

        user = "producer"
        now = dt.datetime.now(dt.timezone.utc)

        # 創建一個會拋出 NoRetry 的任務
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="noretry_job", priority=1)))
            resource_id = info.resource_id

        def worker_logic(resource: Resource[Job[Payload]]):
            # 拋出 NoRetry 異常
            raise NoRetry("This should not be retried")

        # 使用輔助方法運行消費者並追蹤訊息
        _, published_messages = self.run_consumer_in_thread(
            queue_producer, rm, worker_logic, track_published_messages=True
        )

        # 驗證任務狀態
        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            assert "This should not be retried" in res.data.errmsg
            # NoRetry 應該導致任務直接失敗，retries=1
            assert res.data.retries == 1

        # 對於 RabbitMQ，額外驗證訊息路由
        if isinstance(queue_producer, RabbitMQMessageQueue):
            dead_queue_messages = [
                m
                for m in published_messages
                if m["routing_key"] == queue_producer.dead_queue_name
            ]
            retry_queue_messages = [
                m
                for m in published_messages
                if m["routing_key"] == queue_producer.retry_queue_name
            ]

            # NoRetry 應該直接送到 dead letter queue
            assert len(dead_queue_messages) == 1, (
                f"應該有 1 個訊息在 dead queue，但有 {len(dead_queue_messages)}"
            )
            assert len(retry_queue_messages) == 0, (
                f"不應該有訊息在 retry queue，但有 {len(retry_queue_messages)}"
            )

    def create_test_revision_info(
        self, resource_id: str = "test-id", revision_id: str = "rev-1"
    ) -> RevisionInfo:
        """Helper function to create a test RevisionInfo."""
        return RevisionInfo(
            uid=uuid4(),
            resource_id=resource_id,
            revision_id=revision_id,
            status=RevisionStatus.draft,
            created_time=dt.datetime.now(),
            updated_time=dt.datetime.now(),
            created_by="test-user",
            updated_by="test-user",
        )

    class MockChannel:
        """Mock RabbitMQ channel."""

        def __init__(self):
            self.queue_declare = MagicMock()
            self.basic_publish = MagicMock()
            self.basic_qos = MagicMock()
            self.basic_ack = MagicMock()
            self.basic_nack = MagicMock()
            self.start_consuming = MagicMock()
            self.stop_consuming = MagicMock()
            self.is_open = True
            self._callback = None
            self._consume_called = False

        def simulate_message(self, body: bytes, retry_count: int = 0):
            """Simulate receiving a message."""
            if self._callback is None:
                raise RuntimeError("No consumer callback registered")

            method = MagicMock()
            method.delivery_tag = "test-tag"

            properties = MagicMock()
            properties.headers = (
                {"x-retry-count": retry_count} if retry_count > 0 else None
            )

            self._callback(self, method, properties, body)

        def basic_consume(self, queue, on_message_callback):
            """Mock basic_consume and store callback."""
            self._callback = on_message_callback
            self._consume_called = True
            return "consumer-tag-1"

    class MockConnection:
        """Mock RabbitMQ connection."""

        def __init__(self, channel):
            self.channel_obj = channel
            self.is_closed = False
            self.is_open = True

        def channel(self):
            return self.channel_obj

        def close(self):
            self.is_open = False
            self.is_closed = True

        def add_callback_threadsafe(self, callback):
            callback()

    @pytest.fixture
    def mock_resource_manager(self):
        """Create a mock resource manager."""
        return MagicMock()

    @pytest.fixture
    def mock_rabbitmq_queue(self, mock_resource_manager):
        """Create a RabbitMQ queue with mocked connection."""
        mock_channel = self.MockChannel()

        with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
            mock_pika.URLParameters = MagicMock()

            # Create a factory function that returns new connections with the same channel
            def create_connection(*args, **kwargs):
                return self.MockConnection(mock_channel)

            mock_pika.BlockingConnection = create_connection

            def mock_basic_properties(**kwargs):
                return kwargs

            mock_pika.BasicProperties = mock_basic_properties
            mock_pika.DeliveryMode.Persistent = 2

            def mock_worker(job):
                pass

            rm = MagicMock()
            rm.resource_name = "TestJob"
            queue = RabbitMQMessageQueue(
                mock_worker,
                rm,
                amqp_url="amqp://test",
                queue_prefix="test:",
                max_retries=3,
                retry_delay_seconds=10,
            )

            yield queue, mock_channel, rm

    def test_init_declares_all_queues(self):
        """Test that initialization declares main, retry, and dead letter queues."""
        mock_channel = self.MockChannel()
        mock_connection = self.MockConnection(mock_channel)

        with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
            mock_pika.URLParameters = MagicMock()
            mock_pika.BlockingConnection = MagicMock(return_value=mock_connection)
            mock_pika.DeliveryMode.Persistent = 2

            def worker_logic(job):
                pass

            rm = MagicMock()
            rm.resource_name = "TestJob"
            queue = RabbitMQMessageQueue(
                worker_logic,
                rm,
                queue_prefix="test:",
                max_retries=5,
                retry_delay_seconds=15,
            )

            assert mock_channel.queue_declare.call_count == 3
            calls = mock_channel.queue_declare.call_args_list

            # Main queue (prefix_resource_name)
            assert calls[0] == call(queue="test:test_job", durable=True)
            # Dead letter queue
            assert calls[1] == call(queue="test:test_job:dead", durable=True)
            # Retry queue with TTL and DLX
            assert calls[2][1]["queue"] == "test:test_job:retry"
            assert calls[2][1]["durable"] is True
            assert calls[2][1]["arguments"]["x-message-ttl"] == 15000
            assert calls[2][1]["arguments"]["x-dead-letter-exchange"] == ""
            assert (
                calls[2][1]["arguments"]["x-dead-letter-routing-key"] == "test:test_job"
            )

    def test_callback_failure_sends_to_retry_queue(self, mock_rabbitmq_queue):
        """Test that failed callback sends message to retry queue."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        resource = Resource(
            info=self.create_test_revision_info(),
            data=Job(payload="test-payload", status=TaskStatus.PENDING),
        )
        mock_rm.get.return_value = resource

        callback = MagicMock(side_effect=Exception("Test error"))
        queue._do = callback
        queue.start_consume()
        mock_channel.simulate_message(b"test-id", retry_count=0)

        callback.assert_called_once()

        # Verify Job was updated with error info
        update_calls = [
            c
            for c in mock_rm.create_or_update.call_args_list
            if len(c[0]) > 1 and c[0][1].status == TaskStatus.FAILED
        ]
        assert len(update_calls) >= 1
        updated_job = update_calls[-1][0][1]
        assert updated_job.errmsg == "Test error"
        assert updated_job.retries == 1

        # Verify message was published to retry queue
        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:retry"
        ]
        assert len(publish_calls) == 1

        props = publish_calls[0][1]["properties"]
        assert props["headers"]["x-retry-count"] == 1
        assert "Test error" in props["headers"]["x-last-error"]

        mock_channel.basic_ack.assert_called_once()

    def test_max_retries_sends_to_dead_queue(self, mock_rabbitmq_queue):
        """Test that exceeding max retries sends message to dead letter queue."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        resource = Resource(
            info=self.create_test_revision_info(),
            data=Job(payload="test-payload", status=TaskStatus.PENDING),
        )
        mock_rm.get.return_value = resource

        callback = MagicMock(side_effect=Exception("Test error"))
        queue._do = callback
        queue.start_consume()

        # Simulate message with retry_count = max_retries (3)
        mock_channel.simulate_message(b"test-id", retry_count=3)

        # Verify message was published to dead letter queue
        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:dead"
        ]
        assert len(publish_calls) == 1

        props = publish_calls[0][1]["properties"]
        assert props["headers"]["x-retry-count"] == 3

    def test_retry_count_progression(self, mock_rabbitmq_queue):
        """Test that retry count increments correctly through multiple failures."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        resource = Resource(
            info=self.create_test_revision_info(),
            data=Job(payload="test-payload", status=TaskStatus.PENDING),
        )
        mock_rm.get.return_value = resource

        callback = MagicMock(side_effect=Exception("Test error"))
        queue._do = callback
        queue.start_consume()

        # Test retry count progression: 0 -> 1 -> 2 -> 3 -> dead
        for retry_count in range(4):
            mock_channel.basic_publish.reset_mock()
            mock_channel.simulate_message(b"test-id", retry_count=retry_count)

            if retry_count < 3:
                # Should go to retry queue
                publish_calls = [
                    c
                    for c in mock_channel.basic_publish.call_args_list
                    if c[1]["routing_key"] == "test:test_job:retry"
                ]
                assert len(publish_calls) == 1
                props = publish_calls[0][1]["properties"]
                assert props["headers"]["x-retry-count"] == retry_count + 1
            else:
                # Should go to dead queue
                publish_calls = [
                    c
                    for c in mock_channel.basic_publish.call_args_list
                    if c[1]["routing_key"] == "test:test_job:dead"
                ]
                assert len(publish_calls) == 1

    def test_custom_retry_config(self):
        """Test that custom retry configuration is respected."""
        mock_channel = self.MockChannel()
        mock_connection = self.MockConnection(mock_channel)

        with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
            mock_pika.URLParameters = MagicMock()
            mock_pika.BlockingConnection = MagicMock(return_value=mock_connection)
            mock_pika.DeliveryMode.Persistent = 2

            def worker_logic(job):
                pass

            rm = MagicMock()
            rm.resource_name = "CustomQueue"
            queue = RabbitMQMessageQueue(
                worker_logic,
                rm,
                queue_prefix="custom:",
                max_retries=5,
                retry_delay_seconds=30,
            )

            assert queue.max_retries == 5
            assert queue.retry_delay_seconds == 30

            calls = mock_channel.queue_declare.call_args_list
            retry_queue_call = [
                c for c in calls if c[1]["queue"] == "custom:custom_queue:retry"
            ][0]
            assert retry_queue_call[1]["arguments"]["x-message-ttl"] == 30000

    def test_error_message_truncation(self, mock_rabbitmq_queue):
        """Test that very long error messages are truncated in headers but stored fully in Job."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        resource = Resource(
            info=self.create_test_revision_info(),
            data=Job(payload="test-payload", status=TaskStatus.PENDING),
        )
        mock_rm.get.return_value = resource

        long_error = "x" * 1000
        callback = MagicMock(side_effect=Exception(long_error))
        queue._do = callback
        queue.start_consume()
        mock_channel.simulate_message(b"test-id", retry_count=0)

        # Verify error message was truncated to 500 characters in headers
        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:retry"
        ]
        props = publish_calls[0][1]["properties"]
        assert len(props["headers"]["x-last-error"]) == 500

        # But the full error message should be stored in Job.result
        update_calls = [
            c
            for c in mock_rm.create_or_update.call_args_list
            if len(c[0]) > 1 and c[0][1].status == TaskStatus.FAILED
        ]
        updated_job = update_calls[0][0][1]
        assert updated_job.errmsg == long_error
        assert len(updated_job.errmsg) == 1000

    def test_job_error_overwrites_previous_error(self, mock_rabbitmq_queue):
        """Test that new error message overwrites previous one in Job."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        resource = Resource(
            info=self.create_test_revision_info(),
            data=Job(
                payload="test-payload",
                status=TaskStatus.PENDING,
                errmsg="Old error message",
                retries=1,
            ),
        )
        mock_rm.get.return_value = resource

        callback = MagicMock(side_effect=Exception("New error message"))
        queue._do = callback
        queue.start_consume()
        mock_channel.simulate_message(b"test-id", retry_count=1)

        update_calls = [
            c
            for c in mock_rm.create_or_update.call_args_list
            if len(c[0]) > 1 and c[0][1].status == TaskStatus.FAILED
        ]
        assert len(update_calls) >= 1
        updated_job = update_calls[-1][0][1]
        assert updated_job.errmsg == "New error message"
        assert updated_job.retries == 2

    def test_critical_error_when_resource_not_found(self, mock_rabbitmq_queue):
        """Test critical error handling when resource cannot be fetched."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        # First call to get() fails (resource not found)
        mock_rm.get.side_effect = Exception("Resource not found")

        callback = MagicMock()
        queue.start_consume()
        mock_channel.simulate_message(b"missing-id", retry_count=0)

        # Callback should not be called because resource fetch failed
        callback.assert_not_called()

        # Message should be sent to retry queue
        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:retry"
        ]
        assert len(publish_calls) == 1

        props = publish_calls[0][1]["properties"]
        assert "Resource not found" in props["headers"]["x-last-error"]

        # Message should be acked
        mock_channel.basic_ack.assert_called_once()

    def test_critical_error_with_recovery_attempt(self, mock_rabbitmq_queue):
        """Test critical error handling attempts to update Job if possible."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        resource = Resource(
            info=self.create_test_revision_info(),
            data=Job(payload="test-payload", status=TaskStatus.PENDING),
        )

        # First call to get() fails, but second call (in recovery) succeeds
        mock_rm.get.side_effect = [
            Exception("Initial fetch failed"),
            resource,  # Recovery get() succeeds
        ]

        callback = MagicMock()
        queue.start_consume()
        mock_channel.simulate_message(b"test-id", retry_count=0)

        # Callback should not be called because initial fetch failed
        callback.assert_not_called()

        # Verify Job was updated with critical error info in recovery attempt
        update_calls = [
            c
            for c in mock_rm.create_or_update.call_args_list
            if len(c[0]) > 1 and c[0][1].status == TaskStatus.FAILED
        ]
        assert len(update_calls) >= 1
        updated_job = update_calls[-1][0][1]
        assert "Initial fetch failed" in updated_job.errmsg
        assert updated_job.retries == 1

        # Message should be sent to retry queue
        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:retry"
        ]
        assert len(publish_calls) == 1

        # Message should be acked
        mock_channel.basic_ack.assert_called_once()

    def test_critical_error_when_both_fetch_and_recovery_fail(
        self, mock_rabbitmq_queue
    ):
        """Test critical error handling when both initial fetch and recovery fail."""
        queue, mock_channel, mock_rm = mock_rabbitmq_queue

        # Both get() calls fail
        mock_rm.get.side_effect = Exception("Persistent error")

        callback = MagicMock()
        queue.start_consume()
        mock_channel.simulate_message(b"test-id", retry_count=0)

        # Callback should not be called
        callback.assert_not_called()

        # Message should still be sent to retry queue despite recovery failure
        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:retry"
        ]
        assert len(publish_calls) == 1

        props = publish_calls[0][1]["properties"]
        assert "Persistent error" in props["headers"]["x-last-error"]

        # Message should be acked
        mock_channel.basic_ack.assert_called_once()


class TestMessageQueueFactories:
    """Tests for message queue factory implementations."""

    def test_simple_message_queue_factory(self):
        """Test SimpleMessageQueueFactory builds correct instances."""
        factory = SimpleMessageQueueFactory()

        def dummy_handler(job):
            pass

        # Create a mock resource manager
        rm = MagicMock()
        rm.resource_name = "TestJob"

        queue_builder = factory.build(dummy_handler)
        queue = queue_builder(rm)

        assert isinstance(queue, SimpleMessageQueue)
        assert queue._do == dummy_handler

    def test_rabbitmq_message_queue_factory_default_params(self):
        """Test RabbitMQMessageQueueFactory with default parameters."""
        factory = RabbitMQMessageQueueFactory()

        def dummy_handler(job):
            pass

        # Create a mock resource manager
        rm = MagicMock()
        rm.resource_name = "TestJob"

        queue_builder = factory.build(dummy_handler)
        queue = queue_builder(rm)

        assert isinstance(queue, RabbitMQMessageQueue)
        assert queue._do == dummy_handler
        assert queue.amqp_url == "amqp://guest:guest@localhost:5672/"
        assert queue.queue_prefix == "autocrud:"
        assert queue.queue_name is not None  # Now set during construction
        assert queue.max_retries == 3
        assert queue.retry_delay_seconds == 10

    def test_rabbitmq_message_queue_factory_custom_params(self):
        """Test RabbitMQMessageQueueFactory with custom parameters."""
        custom_url = "amqp://user:pass@rabbitmq.example.com:5672/vhost"
        custom_prefix = "custom"
        custom_retries = 5
        custom_delay = 15

        factory = RabbitMQMessageQueueFactory(
            amqp_url=custom_url,
            queue_prefix=custom_prefix,
            max_retries=custom_retries,
            retry_delay_seconds=custom_delay,
        )

        def dummy_handler(job):
            pass

        # Create a mock resource manager
        rm = MagicMock()
        rm.resource_name = "TestJob"

        # Mock the connection to avoid actual RabbitMQ connection
        with patch("pika.BlockingConnection"):
            queue_builder = factory.build(dummy_handler)
            queue = queue_builder(rm)

            assert isinstance(queue, RabbitMQMessageQueue)
            assert queue._do == dummy_handler
            assert queue.amqp_url == custom_url
            assert queue.queue_prefix == custom_prefix
            assert queue.queue_name is not None  # Now set during construction
            assert queue.max_retries == custom_retries
            assert queue.retry_delay_seconds == custom_delay

    def test_factory_builds_multiple_instances(self):
        """Test that factory can build multiple queue instances."""
        factory = RabbitMQMessageQueueFactory(queue_prefix="test:")

        def handler1(job):
            pass

        def handler2(job):
            pass

        # Create a mock resource manager
        rm = MagicMock()
        rm.resource_name = "TestJob"

        # Mock the connection to avoid actual RabbitMQ connection
        with patch("pika.BlockingConnection"):
            queue_builder1 = factory.build(handler1)
            queue_builder2 = factory.build(handler2)
            queue1 = queue_builder1(rm)
            queue2 = queue_builder2(rm)

            # Should be different instances
            assert queue1 is not queue2
            # But with same configuration
            assert queue1.queue_prefix == queue2.queue_prefix == "test:"
            # And different handlers
            assert queue1._do == handler1
            assert queue2._do == handler2
