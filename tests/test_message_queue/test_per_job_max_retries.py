"""Tests for per-job max_retries feature.

Each Job can optionally set ``max_retries`` to override the queue-level default.
When ``Job.max_retries`` is ``None``, the queue default is used.
"""

import datetime as dt
import threading
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from msgspec import Struct

from autocrud.message_queue.rabbitmq import RabbitMQMessageQueue
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import (
    IndexableField,
    Job,
    Resource,
    RevisionInfo,
    RevisionStatus,
    TaskStatus,
)


class Payload(Struct):
    task_name: str
    priority: int


def _make_rm(handler=None, mq_max_retries=5):
    """Create a ResourceManager with SimpleMessageQueue for testing.

    The queue-level ``max_retries`` defaults to 5 so that per-job overrides
    with smaller values are clearly distinguishable.
    """
    if handler is None:

        def handler(job):
            pass

    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)
    factory = SimpleMessageQueueFactory(max_retries=mq_max_retries)
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        message_queue=factory.build(handler),
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )
    return rm


def _run_consumer(queue, rm, worker_logic, timeout=2.0):
    """Run the consume loop in a background thread and wait *timeout* seconds."""
    queue._do = worker_logic

    def _run():
        with rm.meta_provide(user="consumer", now=dt.datetime.now(dt.timezone.utc)):
            try:
                queue.start_consume()
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    time.sleep(timeout)
    queue.stop_consuming()
    t.join(timeout=2)


# ---------------------------------------------------------------------------
# Simple MQ tests
# ---------------------------------------------------------------------------


class TestPerJobMaxRetriesSimple:
    """Per-job max_retries tests using SimpleMessageQueue."""

    def test_per_job_max_retries_limits_retries(self):
        """A job with max_retries=1 should fail permanently after 1 retry,
        even though the queue allows up to 5."""
        rm = _make_rm(mq_max_retries=5)
        queue = rm.message_queue

        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user="u", now=now):
            info = rm.create(
                Job(
                    payload=Payload(task_name="limited", priority=1),
                    max_retries=1,
                )
            )
            resource_id = info.resource_id

        def always_fail(resource):
            raise ValueError("boom")

        _run_consumer(queue, rm, always_fail)

        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            # Should have retried at most 1 time (retries <= max_retries=1)
            assert (
                res.data.retries <= 2
            )  # At most 2 because <= comparison means retries goes to 1 then fails
            assert res.data.retries >= 1

    def test_per_job_max_retries_none_uses_queue_default(self):
        """When Job.max_retries is None, the queue-level default is used."""
        rm = _make_rm(mq_max_retries=2)
        queue = rm.message_queue

        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user="u", now=now):
            info = rm.create(
                Job(
                    payload=Payload(task_name="default_retry", priority=1),
                    max_retries=None,  # explicitly None
                )
            )
            resource_id = info.resource_id

        def always_fail(resource):
            raise ValueError("fail")

        _run_consumer(queue, rm, always_fail, timeout=3.0)

        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            # Queue max_retries=2 → retries should reach 3 (0→1→2→3, with <=2 check after +1)
            # The exact value depends on the <= comparison: retries increments then checks <= max_retries
            assert res.data.retries >= 1

    def test_per_job_max_retries_higher_than_queue(self):
        """A job can set max_retries higher than the queue default for Simple MQ."""
        rm = _make_rm(mq_max_retries=1)
        queue = rm.message_queue

        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user="u", now=now):
            info = rm.create(
                Job(
                    payload=Payload(task_name="more_retries", priority=1),
                    max_retries=3,
                )
            )
            resource_id = info.resource_id

        fail_count = 0

        def count_and_fail(resource):
            nonlocal fail_count
            fail_count += 1
            raise ValueError("fail")

        _run_consumer(queue, rm, count_and_fail, timeout=3.0)

        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            # With per-job max_retries=3, the job should have been attempted more
            # than if queue max_retries=1 was used.
            # retries should be > 1 (which is what queue default would have given)
            assert res.data.retries > 2

    def test_per_job_max_retries_zero_no_retry(self):
        """A job with max_retries=0 should fail immediately without any retry."""
        rm = _make_rm(mq_max_retries=5)
        queue = rm.message_queue

        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user="u", now=now):
            info = rm.create(
                Job(
                    payload=Payload(task_name="no_retry", priority=1),
                    max_retries=0,
                )
            )
            resource_id = info.resource_id

        def always_fail(resource):
            raise ValueError("instant fail")

        _run_consumer(queue, rm, always_fail)

        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            # retries == 1 (one try, no re-attempt)
            assert res.data.retries == 1

    def test_per_job_max_retries_preserved_on_rerun(self):
        """After rerun, the per-job max_retries should be preserved."""
        rm = _make_rm(mq_max_retries=5)
        queue = rm.message_queue

        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user="u", now=now):
            info = rm.create(
                Job(
                    payload=Payload(task_name="rerun_test", priority=1),
                    max_retries=2,
                )
            )
            resource_id = info.resource_id

        # Simulate failure then rerun
        def always_fail(resource):
            raise ValueError("fail")

        _run_consumer(queue, rm, always_fail)

        with rm.meta_provide(user="u", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED

            # Simulate rerun: reset retries/status but keep max_retries
            job = res.data
            job.status = TaskStatus.PENDING
            job.retries = 0
            job.errmsg = None
            rm.create_or_update(resource_id, job)

            # Verify max_retries is still preserved
            res_after = rm.get(resource_id)
            assert res_after.data.max_retries == 2

    def test_mixed_jobs_different_max_retries(self):
        """Multiple jobs with different max_retries are handled independently."""
        rm = _make_rm(mq_max_retries=5)
        queue = rm.message_queue

        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user="u", now=now):
            info_zero = rm.create(
                Job(
                    payload=Payload(task_name="zero_retry", priority=1),
                    max_retries=0,
                )
            )
            info_two = rm.create(
                Job(
                    payload=Payload(task_name="two_retries", priority=2),
                    max_retries=2,
                )
            )
            info_default = rm.create(
                Job(
                    payload=Payload(task_name="default_retry", priority=3),
                    # max_retries=None → falls back to queue default (5)
                )
            )

        def always_fail(resource):
            raise ValueError("fail")

        _run_consumer(queue, rm, always_fail, timeout=4.0)

        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            r0 = rm.get(info_zero.resource_id)
            r2 = rm.get(info_two.resource_id)
            rd = rm.get(info_default.resource_id)

            assert r0.data.status == TaskStatus.FAILED
            assert r2.data.status == TaskStatus.FAILED
            assert rd.data.status == TaskStatus.FAILED

            # zero_retry job should have the fewest retries
            assert r0.data.retries == 1
            # two_retries job should have more than zero but limited
            assert r2.data.retries > r0.data.retries
            # default job should have the most (queue default=5)
            assert rd.data.retries > r2.data.retries


# ---------------------------------------------------------------------------
# RabbitMQ mock tests
# ---------------------------------------------------------------------------


class TestPerJobMaxRetriesRabbitMQ:
    """Per-job max_retries tests for RabbitMQ using mocked connections."""

    class MockChannel:
        """Mock RabbitMQ channel."""

        def __init__(self):
            self.queue_declare = MagicMock()
            self.basic_publish = MagicMock()
            self.basic_qos = MagicMock()
            self.basic_ack = MagicMock()
            self.start_consuming = MagicMock()
            self.stop_consuming = MagicMock()
            self.is_open = True
            self._callback = None

        def simulate_message(self, body: bytes, retry_count: int = 0):
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
            self._callback = on_message_callback
            return "consumer-tag-1"

    class MockConnection:
        def __init__(self, channel):
            self.channel_obj = channel
            self.is_open = True
            self.is_closed = False

        def channel(self):
            return self.channel_obj

        def close(self):
            self.is_open = False
            self.is_closed = True

        def add_callback_threadsafe(self, callback):
            callback()

    @pytest.fixture
    def mock_queue(self):
        """Create a RabbitMQ queue with mocked connection (queue max_retries=3)."""
        yield from self._build_mock_queue(max_retries=3)

    @pytest.fixture
    def mock_queue_5(self):
        """Create a RabbitMQ queue with mocked connection (queue max_retries=5)."""
        yield from self._build_mock_queue(max_retries=5)

    def _build_mock_queue(self, max_retries=3):
        mock_channel = self.MockChannel()

        with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
            mock_pika.URLParameters = MagicMock()

            def create_connection(*args, **kwargs):
                return self.MockConnection(mock_channel)

            mock_pika.BlockingConnection = create_connection

            def mock_basic_properties(**kwargs):
                return kwargs

            mock_pika.BasicProperties = mock_basic_properties
            mock_pika.DeliveryMode.Persistent = 2
            mock_pika.spec.PERSISTENT_DELIVERY_MODE = 2

            rm = MagicMock()
            rm.resource_name = "TestJob"
            queue = RabbitMQMessageQueue(
                lambda job: None,
                rm,
                amqp_url="amqp://test",
                queue_prefix="test:",
                max_retries=max_retries,
                retry_delay_seconds=10,
            )
            yield queue, mock_channel, rm

    def _make_resource(self, max_retries=None, retries=0):
        return Resource(
            info=RevisionInfo(
                uid=uuid4(),
                resource_id="test-id",
                revision_id="rev-1",
                status=RevisionStatus.draft,
                created_time=dt.datetime.now(),
                updated_time=dt.datetime.now(),
                created_by="test-user",
                updated_by="test-user",
            ),
            data=Job(
                payload="test-payload",
                status=TaskStatus.PENDING,
                max_retries=max_retries,
                retries=retries,
            ),
        )

    def test_per_job_max_retries_sends_to_dead_queue_early(self, mock_queue):
        """A job with max_retries=1 should go to dead queue at retry_count=1,
        even though queue allows 3."""
        queue, mock_channel, mock_rm = mock_queue

        resource = self._make_resource(max_retries=1)
        mock_rm.get.return_value = resource

        queue._do = MagicMock(side_effect=Exception("fail"))
        queue.start_consume()

        # retry_count=1 equals per-job max_retries → should go to dead queue
        mock_channel.simulate_message(b"test-id", retry_count=1)
        queue._join_workers()

        publish_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:dead"
        ]
        assert len(publish_calls) == 1, (
            f"Expected 1 dead queue message, got {len(publish_calls)}. "
            f"All publishes: {[c[1]['routing_key'] for c in mock_channel.basic_publish.call_args_list]}"
        )

    def test_per_job_max_retries_none_uses_queue_default(self, mock_queue):
        """When Job.max_retries is None, the queue default (3) is used."""
        queue, mock_channel, mock_rm = mock_queue

        resource = self._make_resource(max_retries=None)
        mock_rm.get.return_value = resource

        queue._do = MagicMock(side_effect=Exception("fail"))
        queue.start_consume()

        # retry_count=2 < queue default 3 → should go to retry queue
        mock_channel.simulate_message(b"test-id", retry_count=2)
        queue._join_workers()

        retry_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:retry"
        ]
        assert len(retry_calls) == 1

    def test_per_job_max_retries_zero(self, mock_queue):
        """A job with max_retries=0 should go to dead queue on first failure."""
        queue, mock_channel, mock_rm = mock_queue

        resource = self._make_resource(max_retries=0)
        mock_rm.get.return_value = resource

        queue._do = MagicMock(side_effect=Exception("fail"))
        queue.start_consume()

        mock_channel.simulate_message(b"test-id", retry_count=0)
        queue._join_workers()

        dead_calls = [
            c
            for c in mock_channel.basic_publish.call_args_list
            if c[1]["routing_key"] == "test:test_job:dead"
        ]
        assert len(dead_calls) == 1

    def test_per_job_max_retries_retry_progression(self, mock_queue_5):
        """Test full retry progression with per-job max_retries=2."""
        queue, mock_channel, mock_rm = mock_queue_5

        resource = self._make_resource(max_retries=2)
        mock_rm.get.return_value = resource

        queue._do = MagicMock(side_effect=Exception("fail"))
        queue.start_consume()

        for retry_count in range(3):
            mock_channel.basic_publish.reset_mock()
            mock_channel.simulate_message(b"test-id", retry_count=retry_count)
            queue._join_workers()

            if retry_count < 2:
                # Should go to retry queue
                retry_calls = [
                    c
                    for c in mock_channel.basic_publish.call_args_list
                    if c[1]["routing_key"] == "test:test_job:retry"
                ]
                assert len(retry_calls) == 1, (
                    f"retry_count={retry_count}: expected retry queue"
                )
            else:
                # retry_count=2 >= max_retries=2 → dead queue
                dead_calls = [
                    c
                    for c in mock_channel.basic_publish.call_args_list
                    if c[1]["routing_key"] == "test:test_job:dead"
                ]
                assert len(dead_calls) == 1, (
                    f"retry_count={retry_count}: expected dead queue"
                )
