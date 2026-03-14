"""Tests for RabbitMQ long-running job support.

Verifies that:
1. Job execution runs on a worker thread (not blocking pika I/O thread).
2. AMQP heartbeat is explicitly configured on connections.
3. HeartbeatThread (application-level) is started during RabbitMQ job execution.
4. ACK/NACK is delivered via ``add_callback_threadsafe`` from the worker thread.
5. BaseException safety net nacks and requeues the message.
6. Factory forwards ``amqp_heartbeat_seconds``.
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from msgspec import Struct

from autocrud.message_queue.rabbitmq import (
    RabbitMQMessageQueue,
    RabbitMQMessageQueueFactory,
)
from autocrud.types import (
    Job,
    Resource,
    RevisionInfo,
    RevisionStatus,
)


class Payload(Struct):
    task_name: str
    priority: int = 1


def _make_revision_info(resource_id: str = "test-id") -> RevisionInfo:
    return RevisionInfo(
        uid=uuid4(),
        resource_id=resource_id,
        revision_id="rev-1",
        status=RevisionStatus.draft,
        created_time=dt.datetime.now(),
        updated_time=dt.datetime.now(),
        created_by="test-user",
        updated_by="test-user",
    )


# ── Helpers ──────────────────────────────────────────────────────────


class MockChannel:
    """Minimal mock channel for unit tests."""

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

    def basic_consume(self, queue, on_message_callback):
        self._callback = on_message_callback
        return "consumer-tag"

    def simulate_message(self, body: bytes, retry_count: int = 0):
        if self._callback is None:
            raise RuntimeError("No consumer callback registered")
        method = MagicMock()
        method.delivery_tag = f"tag-{id(body)}"
        properties = MagicMock()
        properties.headers = {"x-retry-count": retry_count} if retry_count > 0 else None
        self._callback(self, method, properties, body)


class MockConnection:
    def __init__(self, channel):
        self.channel_obj = channel
        self.is_open = True

    def channel(self):
        return self.channel_obj

    def close(self):
        self.is_open = False

    def add_callback_threadsafe(self, callback):
        callback()


@pytest.fixture()
def make_queue(request):
    """Pytest fixture that builds a ``RabbitMQMessageQueue`` with mocked pika.

    Returns a factory function.  The pika patcher is automatically stopped
    at fixture teardown, so tests never leak mocked pika into other files.

    Usage inside a test::

        def test_xxx(self, make_queue):
            queue, ch, rm = make_queue(handler)
    """
    _patchers: list = []

    def _factory(handler=None, *, amqp_heartbeat_seconds=None, mock_channel=None):
        ch = mock_channel or MockChannel()

        patcher = patch("autocrud.message_queue.rabbitmq.pika")
        mock_pika = patcher.start()
        _patchers.append(patcher)
        mock_pika.URLParameters = MagicMock()

        def create_conn(*a, **kw):
            return MockConnection(ch)

        mock_pika.BlockingConnection = create_conn
        mock_pika.BasicProperties = lambda **kw: kw
        mock_pika.spec.PERSISTENT_DELIVERY_MODE = 2

        rm = MagicMock()
        rm.resource_name = "TestJob"

        kwargs = dict(
            do=handler or (lambda job: None),
            resource_manager=rm,
            amqp_url="amqp://test",
            queue_prefix="test:",
            max_retries=3,
            retry_delay_seconds=10,
        )
        if amqp_heartbeat_seconds is not None:
            kwargs["amqp_heartbeat_seconds"] = amqp_heartbeat_seconds
        queue = RabbitMQMessageQueue(**kwargs)
        return queue, ch, rm

    yield _factory

    for p in _patchers:
        p.stop()


# ── Tests ────────────────────────────────────────────────────────────


class TestAMQPHeartbeatParameter:
    """_get_connection() should explicitly set the AMQP heartbeat on connection params."""

    def test_default_heartbeat_is_set(self, make_queue):
        """Default amqp_heartbeat_seconds should be 600."""
        queue, _ch, _rm = make_queue()
        assert queue.amqp_heartbeat_seconds == 600

    def test_custom_heartbeat_is_stored(self, make_queue):
        """Constructor should accept and store a custom value."""
        queue, _ch, _rm = make_queue(amqp_heartbeat_seconds=300)
        assert queue.amqp_heartbeat_seconds == 300

    def test_heartbeat_applied_to_url_params(self):
        """_get_connection should set params.heartbeat before creating BlockingConnection."""
        with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
            params_instance = MagicMock()
            mock_pika.URLParameters.return_value = params_instance
            mock_conn = MagicMock()
            mock_conn.is_open = True
            mock_pika.BlockingConnection.return_value = mock_conn
            mock_pika.spec.PERSISTENT_DELIVERY_MODE = 2

            rm = MagicMock()
            rm.resource_name = "Test"
            q = RabbitMQMessageQueue(
                do=lambda j: None,
                resource_manager=rm,
                amqp_url="amqp://test",
                amqp_heartbeat_seconds=120,
            )
            # _get_connection was called during __init__ (_declare_queues).
            # Verify heartbeat was set on params before BlockingConnection was called.
            assert params_instance.heartbeat == 120


class TestWorkerThreadExecution:
    """Job handler should execute on a separate thread, not on the pika I/O thread."""

    def test_callback_runs_on_worker_thread(self, make_queue):
        """The user handler should run on a thread different from the one calling callback."""
        io_thread_id = threading.current_thread().ident
        handler_thread_ids: list[int] = []
        handler_done = threading.Event()

        def handler(job):
            handler_thread_ids.append(threading.current_thread().ident)
            handler_done.set()

        queue, ch, rm = make_queue(handler)

        resource = Resource(
            info=_make_revision_info(),
            data=Job(payload=Payload(task_name="thread-test")),
        )
        rm.get.return_value = resource

        # Manually set connection so _execute_job can use it
        conn = MockConnection(ch)
        queue._consuming_connection = conn

        method = MagicMock()
        method.delivery_tag = "thread-tag"
        queue._execute_job(ch, method, resource, retry_count=0)

        # Wait for the worker thread to finish (with timeout)
        handler_done.wait(timeout=5.0)

        assert len(handler_thread_ids) == 1
        assert handler_thread_ids[0] != io_thread_id

    def test_ack_delivered_via_add_callback_threadsafe(self, make_queue):
        """ACK must go through add_callback_threadsafe so it executes on the I/O thread."""
        threadsafe_calls: list = []
        handler_done = threading.Event()

        def handler(job):
            handler_done.set()

        queue, ch, rm = make_queue(handler)
        resource = Resource(
            info=_make_revision_info(),
            data=Job(payload=Payload(task_name="ack-test")),
        )
        rm.get.return_value = resource

        # Manually set _consuming_connection so _execute_job can use it.
        conn = MockConnection(ch)
        queue._consuming_connection = conn
        queue._consuming_channel = ch

        original_cb = conn.add_callback_threadsafe

        def tracking_cb(fn):
            threadsafe_calls.append(fn)
            original_cb(fn)

        conn.add_callback_threadsafe = tracking_cb

        method = MagicMock()
        method.delivery_tag = "ack-tag"
        queue._execute_job(ch, method, resource, retry_count=0)

        handler_done.wait(timeout=5.0)
        # Give worker thread time to schedule ack
        time.sleep(0.5)

        # At least one threadsafe callback should have been invoked (for ACK)
        assert len(threadsafe_calls) >= 1


class TestHeartbeatThreadInRabbitMQ:
    """RabbitMQ _execute_job should start a HeartbeatThread (like SimpleMessageQueue)."""

    def test_heartbeat_thread_started_and_stopped(self, make_queue):
        """HeartbeatThread must be started before handler and stopped after."""
        heartbeat_events: list[str] = []
        handler_done = threading.Event()

        def handler(job):
            handler_done.set()

        queue, ch, rm = make_queue(handler)
        resource = Resource(
            info=_make_revision_info(),
            data=Job(payload=Payload(task_name="hb-test")),
        )
        rm.get.return_value = resource

        with patch(
            "autocrud.message_queue.heartbeat.HeartbeatThread",
        ) as MockHB:
            hb_instance = MagicMock()
            MockHB.return_value = hb_instance
            hb_instance.start.side_effect = lambda: heartbeat_events.append("start")
            hb_instance.stop.side_effect = lambda: heartbeat_events.append("stop")

            # Manually set connection so _execute_job can use it
            conn = MockConnection(ch)
            queue._consuming_connection = conn

            method = MagicMock()
            method.delivery_tag = "hb-tag"
            queue._execute_job(ch, method, resource, retry_count=0)

            handler_done.wait(timeout=5.0)
            time.sleep(0.5)

            MockHB.assert_called_once()
            assert heartbeat_events == ["start", "stop"]

    def test_heartbeat_thread_stopped_on_exception(self, make_queue):
        """HeartbeatThread must be stopped even when handler raises."""
        handler_done = threading.Event()

        def handler(job):
            handler_done.set()
            raise RuntimeError("boom")

        queue, ch, rm = make_queue(handler)
        resource = Resource(
            info=_make_revision_info(),
            data=Job(payload=Payload(task_name="hb-exc")),
        )
        rm.get.return_value = resource

        with patch(
            "autocrud.message_queue.heartbeat.HeartbeatThread",
        ) as MockHB:
            hb_instance = MagicMock()
            MockHB.return_value = hb_instance

            # Manually set connection so _execute_job can use it
            conn = MockConnection(ch)
            queue._consuming_connection = conn

            method = MagicMock()
            method.delivery_tag = "hb-exc-tag"
            queue._execute_job(ch, method, resource, retry_count=0)

            handler_done.wait(timeout=5.0)
            time.sleep(0.5)

            hb_instance.start.assert_called_once()
            hb_instance.stop.assert_called_once()


class TestBaseExceptionSafetyNet:
    """If the worker thread encounters a BaseException outside normal except,
    the message should be NACKed with requeue=True."""

    def test_keyboard_interrupt_nacks_with_requeue(self, make_queue):
        """KeyboardInterrupt (BaseException) should result in NACK + requeue."""
        handler_done = threading.Event()

        def handler(job):
            handler_done.set()
            raise KeyboardInterrupt("simulated")

        queue, ch, rm = make_queue(handler)
        resource = Resource(
            info=_make_revision_info(),
            data=Job(payload=Payload(task_name="base-exc")),
        )
        rm.get.return_value = resource

        # Manually set _consuming_connection so _execute_job can use it.
        conn = MockConnection(ch)
        queue._consuming_connection = conn
        queue._consuming_channel = ch

        method = MagicMock()
        method.delivery_tag = "nack-tag"
        queue._execute_job(ch, method, resource, retry_count=0)

        handler_done.wait(timeout=5.0)
        time.sleep(0.5)

        # Should have called basic_nack with requeue=True
        ch.basic_nack.assert_called()
        nack_call = ch.basic_nack.call_args
        assert nack_call[1].get("requeue") is True or (
            len(nack_call[0]) >= 2 and nack_call[0][1] is True
        )


class TestFactoryForwardsHeartbeatSeconds:
    """RabbitMQMessageQueueFactory should accept & forward amqp_heartbeat_seconds."""

    def test_factory_default(self, make_queue):
        # make_queue ensures pika is mocked for RabbitMQMessageQueue construction
        make_queue()  # activate the pika mock
        factory = RabbitMQMessageQueueFactory()
        rm = MagicMock()
        rm.resource_name = "TestJob"
        builder = factory.build(lambda j: None)
        queue = builder(rm)
        assert queue.amqp_heartbeat_seconds == 600

    def test_factory_custom(self, make_queue):
        make_queue()  # activate the pika mock
        factory = RabbitMQMessageQueueFactory(amqp_heartbeat_seconds=120)
        rm = MagicMock()
        rm.resource_name = "TestJob"
        builder = factory.build(lambda j: None)
        queue = builder(rm)
        assert queue.amqp_heartbeat_seconds == 120
