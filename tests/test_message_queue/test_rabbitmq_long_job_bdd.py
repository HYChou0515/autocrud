"""BDD integration tests — real RabbitMQ, zero mocks.

Requires a running RabbitMQ broker at ``localhost:5672`` (guest/guest).
The entire module is **skipped** when the broker is unreachable.

These tests use real pika connections, real worker threads, real
HeartbeatThread, and real ResourceManager with in-memory storage.
They verify *observable outcomes*, not internal wiring.

Background
----------
pika ``BlockingConnection`` uses a single I/O thread: the thread that
calls ``channel.start_consuming()``.  That same thread must answer AMQP
heartbeat frames from the broker.  If the ``on_message_callback``
blocks the I/O thread (old behaviour), the broker closes the connection
after ``2 × heartbeat`` seconds of silence.

The fix moves job execution to a dedicated **worker thread** so that
the I/O thread returns immediately from the callback and stays free to
service heartbeats.

Scenario 1 — Connection survives a long-running job
  GIVEN  amqp_heartbeat_seconds = 3  (broker timeout ≈ 6 s)
    AND  a handler that sleeps for 10 s  (well past the timeout)
  WHEN   the job is created and consumed
  THEN   the job completes with status COMPLETED
    AND  last_heartbeat_at is set  (HeartbeatThread ran during execution)

Scenario 2 — Failed long-running job records error and retries
  GIVEN  a handler that works for 3 s then raises RuntimeError
  WHEN   the job is consumed (and all retries exhaust)
  THEN   job.status == FAILED
    AND  job.errmsg contains the error message
    AND  job.retries >= 1
    AND  last_heartbeat_at is set
"""

from __future__ import annotations

import datetime as dt
import threading
import time
from uuid import uuid4

import pytest
from msgspec import Struct

from autocrud.types import IndexableField, Job, TaskStatus

# ── Gate: skip when RabbitMQ is unreachable ──────────────────────────


def _rabbitmq_reachable() -> bool:
    try:
        import pika

        conn = pika.BlockingConnection(
            pika.URLParameters("amqp://guest:guest@localhost:5672/")
        )
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _rabbitmq_reachable(),
    reason="RabbitMQ is not running at localhost:5672",
)


# ── Payload ──────────────────────────────────────────────────────────


class Payload(Struct):
    task_name: str


# ── Fixture ──────────────────────────────────────────────────────────


@pytest.fixture()
def rmq():
    """Real RabbitMQ queue + ResourceManager with in-memory storage.

    Configuration chosen to trigger the old bug quickly:

      amqp_heartbeat_seconds = 3   → broker closes conn after ~6 s
      _heartbeat_interval    = 1.0 → HeartbeatThread ticks every 1 s
      max_retries            = 2
      retry_delay_seconds    = 1
    """
    from autocrud.message_queue.rabbitmq import RabbitMQMessageQueueFactory
    from autocrud.resource_manager.core import ResourceManager, SimpleStorage
    from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
    from autocrud.resource_manager.resource_store.simple import MemoryResourceStore

    prefix = f"bdd-{uuid4().hex[:8]}:"

    factory = RabbitMQMessageQueueFactory(
        queue_prefix=prefix,
        amqp_heartbeat_seconds=3,
        max_retries=2,
        retry_delay_seconds=1,
    )
    storage = SimpleStorage(MemoryMetaStore(), MemoryResourceStore())
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        message_queue=factory.build(lambda _res: None),
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )
    queue = rm.message_queue
    queue._heartbeat_interval = 1.0  # fast app-level heartbeat

    yield queue, rm

    # Teardown — stop consumer, delete queues
    try:
        queue.stop_consuming()
    except Exception:
        pass
    time.sleep(1)
    try:
        with queue._get_connection() as (_, ch):
            ch.queue_delete(queue.queue_name)
            ch.queue_delete(queue.retry_queue_name)
            ch.queue_delete(queue.dead_queue_name)
    except Exception:
        pass


# ── Helpers ──────────────────────────────────────────────────────────


def _consume_in_background(queue, rm) -> threading.Thread:
    """Start ``queue.start_consume()`` on a daemon thread."""

    def _run():
        with rm.meta_provide(user="consumer", now=dt.datetime.now(dt.timezone.utc)):
            try:
                queue.start_consume()
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True, name="bdd-consumer")
    t.start()
    time.sleep(0.5)  # let consumer register with broker
    return t


def _poll_job(rm, resource_id, *, predicate, timeout=30, interval=0.5):
    """Re-fetch job until ``predicate(resource)`` is True or *timeout*."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with rm.meta_provide(user="poller", now=dt.datetime.now(dt.timezone.utc)):
            res = rm.get(resource_id)
        if predicate(res):
            return res
        time.sleep(interval)
    # Final fetch so the caller can see the actual state in assertion messages
    with rm.meta_provide(user="poller", now=dt.datetime.now(dt.timezone.utc)):
        return rm.get(resource_id)


# ── Scenarios ────────────────────────────────────────────────────────


class TestScenario_ConnectionSurvivesLongJob:
    """
    GIVEN  amqp_heartbeat_seconds = 3   (broker timeout ≈ 6 s)
      AND  a handler that sleeps 10 s   (well past the timeout)
    WHEN   the job is created and consumed
    THEN   the job completes with status COMPLETED
      AND  last_heartbeat_at was updated by HeartbeatThread
      AND  no ConnectionClosedByBroker was raised
    """

    def test_10s_job_completes_with_3s_heartbeat(self, rmq):
        queue, rm = rmq
        completed = threading.Event()

        def long_handler(resource):
            # 10 s >> 2 × 3 s = 6 s — the old code would lose the
            # connection here because the I/O thread was blocked.
            time.sleep(10)
            completed.set()

        queue._do = long_handler

        consumer = _consume_in_background(queue, rm)

        # Create job → rm.create() auto-calls queue.put()
        with rm.meta_provide(user="producer", now=dt.datetime.now(dt.timezone.utc)):
            info = rm.create(Job(payload=Payload(task_name="long-job")))
            resource_id = info.resource_id

        # THEN: handler completed — the connection survived 10 s
        assert completed.wait(timeout=20), (
            "Job did not complete within 20 s — the RabbitMQ connection "
            "was likely closed due to heartbeat timeout (the bug this "
            "fix addresses)"
        )

        # Poll until RM reflects COMPLETED
        res = _poll_job(
            rm,
            resource_id,
            predicate=lambda r: r.data.status == TaskStatus.COMPLETED,
            timeout=5,
        )
        assert res.data.status == TaskStatus.COMPLETED

        # THEN: HeartbeatThread updated last_heartbeat_at during the 10 s job
        assert res.data.last_heartbeat_at is not None, (
            "HeartbeatThread should have updated last_heartbeat_at "
            "at least once during the 10-second job"
        )

        queue.stop_consuming()
        consumer.join(timeout=5)


class TestScenario_FailedLongJobRecordsError:
    """
    GIVEN  a handler that works for 3 s then raises RuntimeError
    WHEN   the job is consumed (and retries exhaust)
    THEN   job.status == FAILED
      AND  job.errmsg contains the error message
      AND  job.retries >= 1
      AND  last_heartbeat_at was set
    """

    def test_error_recorded_after_long_work(self, rmq):
        queue, rm = rmq

        def failing_handler(resource):
            time.sleep(3)  # real work before failure
            raise RuntimeError("data processing failed")

        queue._do = failing_handler

        consumer = _consume_in_background(queue, rm)

        with rm.meta_provide(user="producer", now=dt.datetime.now(dt.timezone.utc)):
            info = rm.create(Job(payload=Payload(task_name="fail-job")))
            resource_id = info.resource_id

        # Poll until all retries are exhausted (max_retries=2)
        res = _poll_job(
            rm,
            resource_id,
            predicate=lambda r: (
                r.data.status == TaskStatus.FAILED and r.data.retries >= 1
            ),
            timeout=30,
        )

        assert res.data.status == TaskStatus.FAILED
        assert "data processing failed" in res.data.errmsg
        assert res.data.retries >= 1

        # HeartbeatThread should have run during the 3 s handler execution
        assert res.data.last_heartbeat_at is not None, (
            "HeartbeatThread should have set last_heartbeat_at during execution"
        )

        queue.stop_consuming()
        consumer.join(timeout=5)
