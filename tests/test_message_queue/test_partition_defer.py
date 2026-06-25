"""#384 — partition_key serialization is honored by RabbitMQ and Celery.

These backends previously *silently ignored* ``partition_key``: the contract
was implemented only in ``SimpleMessageQueue``. Now each multi-worker backend
checks for a PROCESSING peer in the same partition before claiming a job and,
if it finds one, defers the job (re-routing it through a short delay) instead
of running it concurrently. A deferred job is **not** a retry — its retry
budget is untouched.

The checks here are unit-level (mocked broker / mocked ``apply_async``) so
they run in fast CI without a live RabbitMQ or Celery worker; they assert the
*decision* (defer vs. claim), which is the behavior #384 is about.
"""

from contextlib import contextmanager
from unittest.mock import MagicMock

import msgspec
import pytest

from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import IndexableField, Job, TaskStatus


class Payload(msgspec.Struct):
    task_name: str


def _rm():
    """A ResourceManager *not* wired to a message queue, so create() does not
    auto-enqueue. partition_key/status are indexed so the busy-peer search works.
    """
    storage = SimpleStorage(MemoryMetaStore(), MemoryResourceStore())
    return ResourceManager(
        Job[Payload],
        storage=storage,
        indexed_fields=[
            IndexableField(field_path="status", field_type=str),
            IndexableField(field_path="partition_key", field_type=str),
            IndexableField(field_path="idempotency_key", field_type=str),
        ],
        default_user="t",
    )


def _seed_busy_and_candidate(rm):
    """Create a PROCESSING peer and a PENDING candidate, both in partition 'P'.

    Returns the candidate's resource_id.
    """
    rm.create(
        Job(payload=Payload("busy"), partition_key="P", status=TaskStatus.PROCESSING)
    )
    cand = rm.create(
        Job(payload=Payload("cand"), partition_key="P", status=TaskStatus.PENDING)
    )
    return cand.resource_id


# ---------------------------------------------------------------------------
# RabbitMQ
# ---------------------------------------------------------------------------


def test_rabbitmq_pop_defers_when_partition_busy(monkeypatch):
    pytest.importorskip("pika")
    from specstar.message_queue.rabbitmq import RabbitMQMessageQueue

    rm = _rm()
    candidate_id = _seed_busy_and_candidate(rm)

    channel = MagicMock()

    @contextmanager
    def fake_conn(self):
        yield (MagicMock(), channel)

    # Avoid touching a real broker during __init__ and pop().
    monkeypatch.setattr(RabbitMQMessageQueue, "_declare_queues", lambda self: None)
    monkeypatch.setattr(RabbitMQMessageQueue, "_get_connection", fake_conn)

    q = RabbitMQMessageQueue(do=lambda r: None, resource_manager=rm)

    # basic_get hands the consumer the candidate (partition 'P', PENDING).
    method_frame = MagicMock()
    method_frame.delivery_tag = 7
    channel.basic_get.return_value = (method_frame, None, candidate_id.encode("utf-8"))

    result = q.pop()

    # Deferred: nothing claimable right now.
    assert result is None
    # Re-routed through a delay queue (defer) and acked off the main queue.
    channel.basic_publish.assert_called_once()
    channel.basic_ack.assert_called_once_with(7)
    # The candidate was NOT marked PROCESSING (it goes back to wait its turn).
    assert rm.get(candidate_id).data.status == TaskStatus.PENDING


def test_rabbitmq_pop_claims_when_partition_free(monkeypatch):
    pytest.importorskip("pika")
    from specstar.message_queue.rabbitmq import RabbitMQMessageQueue

    rm = _rm()
    # No busy peer this time — a lone PENDING job in partition 'Q'.
    cand = rm.create(
        Job(payload=Payload("solo"), partition_key="Q", status=TaskStatus.PENDING)
    )

    channel = MagicMock()

    @contextmanager
    def fake_conn(self):
        yield (MagicMock(), channel)

    monkeypatch.setattr(RabbitMQMessageQueue, "_declare_queues", lambda self: None)
    monkeypatch.setattr(RabbitMQMessageQueue, "_get_connection", fake_conn)

    q = RabbitMQMessageQueue(do=lambda r: None, resource_manager=rm)

    method_frame = MagicMock()
    method_frame.delivery_tag = 3
    channel.basic_get.return_value = (
        method_frame,
        None,
        cand.resource_id.encode("utf-8"),
    )

    result = q.pop()

    # Claimed normally: returned and marked PROCESSING; no defer publish.
    assert result is not None
    assert result.data.status == TaskStatus.PROCESSING
    channel.basic_publish.assert_not_called()
    channel.basic_ack.assert_called_once_with(3)


# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------


def test_celery_task_defers_when_partition_busy():
    pytest.importorskip("celery")
    from celery import Celery

    from specstar.message_queue.celery_queue import CeleryMessageQueue

    app = Celery("test_partition", broker="memory://", backend="cache+memory://")
    app.conf.update(task_always_eager=True, task_eager_propagates=False)

    rm = _rm()
    candidate_id = _seed_busy_and_candidate(rm)

    q = CeleryMessageQueue(do=lambda r: None, resource_manager=rm, celery_app=app)
    # Record the deferral instead of letting eager mode recurse into it.
    q._celery_task.apply_async = MagicMock()

    # Run the task body eagerly; the deferral raises Ignore which eager mode
    # captures (task_eager_propagates=False).
    q._celery_task.apply(args=(candidate_id, 0))

    q._celery_task.apply_async.assert_called_once()
    _, kwargs = q._celery_task.apply_async.call_args
    assert kwargs["args"] == (candidate_id, 0)  # retry budget preserved
    assert kwargs["countdown"] == q.partition_retry_delay_seconds
    # Candidate never marked PROCESSING.
    assert rm.get(candidate_id).data.status == TaskStatus.PENDING


def test_celery_task_runs_when_partition_free():
    pytest.importorskip("celery")
    from celery import Celery

    from specstar.message_queue.celery_queue import CeleryMessageQueue

    app = Celery("test_partition2", broker="memory://", backend="cache+memory://")
    app.conf.update(task_always_eager=True, task_eager_propagates=False)

    rm = _rm()
    cand = rm.create(
        Job(payload=Payload("solo"), partition_key="Q", status=TaskStatus.PENDING)
    )

    ran = []
    q = CeleryMessageQueue(
        do=lambda r: ran.append(r.info.resource_id),
        resource_manager=rm,
        celery_app=app,
    )
    q._celery_task.apply_async = MagicMock()

    q._celery_task.apply(args=(cand.resource_id, 0))

    # No defer; the handler ran.
    q._celery_task.apply_async.assert_not_called()
    assert ran == [cand.resource_id]
