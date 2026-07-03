"""#409 — stale/killed jobs go through the retry budget.

A worker that is killed (or hangs) mid-job leaves its record in
``PROCESSING``. The sweep (``recover_stale_jobs``) used to mark such a job
terminally ``FAILED`` with zero retries; now it counts the attempt and
requeues it while there is retry budget left, only failing once the budget
is exhausted. On broker backends (RabbitMQ) the re-delivery is instead
classified at consume time by :meth:`_redelivery_decision`.
"""

import datetime as dt

import pytest
from msgspec import Struct

from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import IndexableField, Job, TaskStatus


class Payload(Struct):
    task_name: str


def _make_queue(max_retries: int = 3):
    storage = SimpleStorage(MemoryMetaStore(), MemoryResourceStore())
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        message_queue=SimpleMessageQueueFactory(max_retries=max_retries).build(
            lambda job: None
        ),
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )
    return rm, rm.message_queue


@pytest.fixture
def rm_and_queue():
    return _make_queue()


def _make_processing_job(rm, *, retries: int = 0, max_retries=None) -> str:
    """Create a job already stuck in PROCESSING (simulating a killed worker)."""
    user, now = "u", dt.datetime.now(dt.timezone.utc)
    with rm.using(user=user, now=now):
        info = rm.create(
            Job(payload=Payload(task_name="stuck"), max_retries=max_retries)
        )
        rid = info.resource_id
        r = rm.get(rid)
        r.data.status = TaskStatus.PROCESSING
        r.data.retries = retries
        rm.create_or_update(rid, r.data)
    return rid


def _get(rm, rid):
    with rm.using(user="u", now=dt.datetime.now(dt.timezone.utc)):
        return rm.get(rid).data


def test_stale_job_under_budget_is_requeued_pending(rm_and_queue):
    """Stale PROCESSING job with retries under budget → PENDING + retries+1."""
    rm, queue = rm_and_queue
    rid = _make_processing_job(rm, retries=0)

    recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)

    assert recovered == [rid]
    job = _get(rm, rid)
    assert job.status == TaskStatus.PENDING  # requeued for retry, not FAILED
    assert job.retries == 1


def test_stale_job_over_budget_is_failed(rm_and_queue):
    """Stale job whose retries would exceed the budget → terminal FAILED."""
    rm, queue = rm_and_queue
    rid = _make_processing_job(rm, retries=3)  # queue default max_retries=3

    recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)

    assert recovered == [rid]
    job = _get(rm, rid)
    assert job.status == TaskStatus.FAILED
    assert job.retries == 4
    assert "exhausted" in job.errmsg


def test_stale_recovery_respects_per_job_max_retries(rm_and_queue):
    """A per-job max_retries=0 fails on the first stale recovery, even though
    the queue default (3) would still have budget."""
    rm, queue = rm_and_queue
    rid = _make_processing_job(rm, retries=0, max_retries=0)

    queue.recover_stale_jobs(heartbeat_timeout_seconds=0)

    job = _get(rm, rid)
    assert job.status == TaskStatus.FAILED
    assert job.retries == 1
