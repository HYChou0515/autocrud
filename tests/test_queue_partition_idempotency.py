"""#342 #3 + #4 — per-partition serialization & idempotent enqueue.

These two queue primitives are what turn a generic job queue into one that's
safe to drive from a public API:

* ``partition_key=`` serializes work-per-key without serializing the *whole*
  queue. Two jobs on the same partition never run concurrently; jobs on
  different partitions still parallelize. The canonical use is "rebuild the
  aggregate for tenant X" — multiple inflight rebuilds for one tenant would
  trample each other, but tenants are independent.

* ``idempotency_key=`` makes enqueue ``exactly-once`` from the caller's
  point of view: a retry of an HTTP request that already enqueued a job
  returns the *original* job, not a duplicate. Standard for retry-prone
  client paths (mobile, webhooks).

Both fields live on the ``Job`` Struct so any backend can opt in; this test
file drives the in-process ``SimpleMessageQueue`` reference implementation.
"""

import msgspec
import pytest

from specstar.message_queue.simple import SimpleMessageQueue, SimpleMessageQueueFactory
from specstar.resource_manager.core import ResourceManager, SimpleStorage
from specstar.resource_manager.meta_store.simple import MemoryMetaStore
from specstar.resource_manager.resource_store.simple import MemoryResourceStore
from specstar.types import (
    IndexableField,
    Job,
    TaskStatus,
)


class Payload(msgspec.Struct):
    task_name: str


def _mk_queue() -> tuple[SimpleMessageQueue[Payload], ResourceManager[Job[Payload]]]:
    """Spin up a fresh in-memory queue + ResourceManager pair."""
    storage = SimpleStorage(MemoryMetaStore(), MemoryResourceStore())

    def _noop_handler(job):  # pragma: no cover — never invoked in these tests
        pass

    factory = SimpleMessageQueueFactory()
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        message_queue=factory.build(_noop_handler),
        indexed_fields=[
            IndexableField(field_path="status", field_type=str),
            IndexableField(field_path="partition_key", field_type=str),
            IndexableField(field_path="idempotency_key", field_type=str),
        ],
        default_user="t",
    )
    return rm.message_queue, rm


# ---------------------------------------------------------------------------
# #342 #3 — partition_key per-key serialization
# ---------------------------------------------------------------------------


def test_job_struct_carries_partition_key_field():
    job = Job(payload=Payload(task_name="x"), partition_key="tenant-7")
    assert job.partition_key == "tenant-7"


def test_enqueue_records_partition_key_on_the_job():
    mq, rm = _mk_queue()
    res = mq.enqueue(Payload(task_name="x"), partition_key="tenant-7")
    stored = rm.get(res.info.resource_id).data
    assert stored.partition_key == "tenant-7"


def test_pop_serializes_jobs_in_the_same_partition():
    # The serialization guarantee: while one job in partition P is PROCESSING,
    # pop() must not hand out another job in P.
    mq, _ = _mk_queue()
    mq.enqueue(Payload(task_name="a"), partition_key="P")
    mq.enqueue(Payload(task_name="b"), partition_key="P")

    first = mq.pop()
    assert first is not None
    assert first.data.payload.task_name == "a"  # FIFO within partition

    # 'b' is blocked while 'a' is PROCESSING
    assert mq.pop() is None


def test_pop_does_not_block_across_partitions():
    # The whole point of partition_key vs. a global lock: independent
    # partitions still parallelize.
    mq, _ = _mk_queue()
    mq.enqueue(Payload(task_name="a"), partition_key="P1")
    mq.enqueue(Payload(task_name="b"), partition_key="P2")

    one = mq.pop()
    two = mq.pop()
    assert one is not None and two is not None
    assert {one.data.payload.task_name, two.data.payload.task_name} == {"a", "b"}


def test_pop_unblocks_partition_after_completion():
    mq, _ = _mk_queue()
    a = mq.enqueue(Payload(task_name="a"), partition_key="P")
    mq.enqueue(Payload(task_name="b"), partition_key="P")

    first = mq.pop()
    assert first is not None
    mq.complete(a.info.resource_id)  # frees the partition

    second = mq.pop()
    assert second is not None
    assert second.data.payload.task_name == "b"


def test_partition_key_none_means_no_serialization():
    # Backward-compat: without a partition_key, the queue behaves as before
    # (every pending job is independently eligible).
    mq, _ = _mk_queue()
    mq.enqueue(Payload(task_name="a"))
    mq.enqueue(Payload(task_name="b"))

    one = mq.pop()
    two = mq.pop()
    assert one is not None and two is not None  # both pop'd, no blocking


# ---------------------------------------------------------------------------
# #342 #4 — idempotency_key on enqueue
# ---------------------------------------------------------------------------


def test_job_struct_carries_idempotency_key_field():
    job = Job(payload=Payload(task_name="x"), idempotency_key="req-42")
    assert job.idempotency_key == "req-42"


def test_enqueue_with_same_idempotency_key_returns_original_job():
    # Same key, same payload → no second job created.
    mq, rm = _mk_queue()
    a = mq.enqueue(Payload(task_name="x"), idempotency_key="req-42")
    b = mq.enqueue(Payload(task_name="x"), idempotency_key="req-42")

    assert a.info.resource_id == b.info.resource_id


def test_enqueue_with_different_idempotency_keys_creates_distinct_jobs():
    mq, _ = _mk_queue()
    a = mq.enqueue(Payload(task_name="x"), idempotency_key="k1")
    b = mq.enqueue(Payload(task_name="x"), idempotency_key="k2")

    assert a.info.resource_id != b.info.resource_id


def test_idempotent_replay_works_even_after_job_completes():
    # The "exactly-once enqueue" contract: a client retry after the job
    # already ran must still resolve to the original record, not a fresh
    # one (otherwise the work runs twice).
    mq, _ = _mk_queue()
    a = mq.enqueue(Payload(task_name="x"), idempotency_key="req-42")
    mq.complete(a.info.resource_id)

    b = mq.enqueue(Payload(task_name="x"), idempotency_key="req-42")
    assert b.info.resource_id == a.info.resource_id
    assert b.data.status == TaskStatus.COMPLETED


def test_idempotency_key_none_creates_independent_jobs():
    # No key → no dedup. Two enqueues of the same payload are two jobs.
    mq, _ = _mk_queue()
    a = mq.enqueue(Payload(task_name="x"))
    b = mq.enqueue(Payload(task_name="x"))

    assert a.info.resource_id != b.info.resource_id


def test_enqueue_with_idempotency_collision_rejects_payload_mismatch():
    # If the caller re-uses an idempotency key with a *different* payload,
    # that's not a benign retry — it's a programming error. Refuse rather
    # than silently returning the original (the caller would never notice
    # their second call's payload was dropped).
    mq, _ = _mk_queue()
    mq.enqueue(Payload(task_name="x"), idempotency_key="req-42")
    with pytest.raises(ValueError, match="idempotency"):
        mq.enqueue(Payload(task_name="y"), idempotency_key="req-42")
