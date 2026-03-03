"""Tests for heartbeat mechanism during job execution.

Heartbeat ensures that if a worker is killed (e.g., OOM), we can distinguish
between 'still running' and 'dead' jobs by checking last_heartbeat_at.

Key design:
- HeartbeatThread runs in background during _execute_job, transparent to worker function
- Heartbeat uses rm.modify (draft revision) to avoid creating new stable revisions
- recover_stale_jobs checks heartbeat timeout before marking as FAILED
- Worker function (_do) is completely unaware of heartbeat
"""

import datetime as dt
import threading
import time

import pytest
from msgspec import Struct

from autocrud.message_queue.basic import NoRetry
from autocrud.message_queue.heartbeat import HeartbeatThread
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import (
    IndexableField,
    Job,
    RevisionStatus,
    TaskStatus,
)


class Payload(Struct):
    task_name: str
    priority: int = 1


@pytest.fixture
def rm_and_queue():
    """Create a ResourceManager and SimpleMessageQueue for testing."""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    def handler(job):
        pass

    mq_factory = SimpleMessageQueueFactory(max_retries=3)
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        message_queue=mq_factory.build(handler),
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )
    queue = rm.message_queue
    return rm, queue


class TestHeartbeatThread:
    """Tests for HeartbeatThread class."""

    def test_heartbeat_updates_last_heartbeat_at(self, rm_and_queue):
        """HeartbeatThread should update last_heartbeat_at during execution."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="hb_test")))
            resource_id = info.resource_id
            # Set to PROCESSING in draft mode (as _execute_job would)
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(resource_id, resource.data, status=RevisionStatus.draft)

        # Start heartbeat with a short interval
        hb = HeartbeatThread(mq=queue, resource_id=resource_id, interval_seconds=0.05)
        hb.start()
        time.sleep(0.2)  # Let a few heartbeats fire
        hb.stop()

        # Verify last_heartbeat_at was set
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.last_heartbeat_at is not None
            # Should be recent (within last 2 seconds)
            elapsed = (
                dt.datetime.now(dt.timezone.utc) - res.data.last_heartbeat_at
            ).total_seconds()
            assert elapsed < 2.0

    def test_heartbeat_uses_modify_not_create_or_update(self, rm_and_queue):
        """HeartbeatThread should use rm.modify (draft) not rm.create_or_update (stable)."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="draft_test")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(resource_id, resource.data, status=RevisionStatus.draft)

        # Get initial revision count
        with rm.meta_provide(user=user, now=now):
            meta_before = rm.get_meta(resource_id)
            revision_count_before = meta_before.total_revision_count

        # Start heartbeat
        hb = HeartbeatThread(mq=queue, resource_id=resource_id, interval_seconds=0.05)
        hb.start()
        time.sleep(0.2)
        hb.stop()

        # Revision count should NOT have increased (modify doesn't create new revisions)
        with rm.meta_provide(user=user, now=now):
            meta_after = rm.get_meta(resource_id)
            assert meta_after.total_revision_count == revision_count_before, (
                "Heartbeat should use modify (draft) and not create new revisions."
            )

    def test_heartbeat_stops_cleanly(self, rm_and_queue):
        """HeartbeatThread should stop without hanging."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="stop_test")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(resource_id, resource.data, status=RevisionStatus.draft)

        hb = HeartbeatThread(mq=queue, resource_id=resource_id, interval_seconds=0.05)
        hb.start()
        time.sleep(0.1)
        hb.stop()

        # Thread should be cleaned up
        assert hb._thread is None
        # No lingering heartbeat threads
        for t in threading.enumerate():
            assert not t.name.startswith(f"heartbeat-{resource_id}")

    def test_heartbeat_resilient_to_storage_error(self, rm_and_queue):
        """HeartbeatThread should not crash if a single modify fails."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="err_test")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(resource_id, resource.data, status=RevisionStatus.draft)

        hb = HeartbeatThread(mq=queue, resource_id=resource_id, interval_seconds=0.05)
        hb.start()

        # Temporarily break modify — heartbeat should not crash
        original_modify = rm.modify
        rm.modify = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("storage down"))
        time.sleep(0.15)

        # Restore and verify thread is still alive
        rm.modify = original_modify
        assert hb._thread is not None and hb._thread.is_alive()
        hb.stop()


class TestExecuteJobWithHeartbeat:
    """Tests that _execute_job automatically manages heartbeat."""

    def test_slow_job_gets_heartbeats(self, rm_and_queue):
        """A slow job should have last_heartbeat_at updated during execution."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="slow_job")))
            resource_id = info.resource_id

        # Pop the job (sets to PROCESSING)
        job_resource = queue.pop()
        assert job_resource is not None

        # Make a slow worker
        def slow_worker(resource):
            time.sleep(0.3)

        queue._do = slow_worker
        queue._heartbeat_interval = 0.05

        queue._execute_job(job_resource)

        # Job should be completed AND have a heartbeat timestamp
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.COMPLETED
            assert res.data.last_heartbeat_at is not None

    def test_heartbeat_stops_after_job_failure(self, rm_and_queue):
        """Heartbeat should stop even if job fails."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="fail_job")))
            resource_id = info.resource_id

        job_resource = queue.pop()
        queue._do = lambda r: (_ for _ in ()).throw(NoRetry("boom"))
        queue._heartbeat_interval = 0.05

        queue._execute_job(job_resource)

        # Job should be FAILED and no lingering heartbeat threads
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED

        for t in threading.enumerate():
            assert not t.name.startswith(f"heartbeat-{resource_id}")

    def test_worker_function_unaware_of_heartbeat(self, rm_and_queue):
        """Worker function should not receive heartbeat-related args."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        received_args = []

        def inspecting_worker(resource):
            received_args.append(resource)
            # Worker should get a normal Resource[Job[Payload]], nothing extra
            assert isinstance(resource.data, Job)
            assert hasattr(resource.data, "payload")

        with rm.meta_provide(user=user, now=now):
            rm.create(Job(payload=Payload(task_name="inspect_job")))

        job_resource = queue.pop()
        queue._do = inspecting_worker
        queue._heartbeat_interval = 0.05

        queue._execute_job(job_resource)

        assert len(received_args) == 1


class TestRecoverStaleJobsWithHeartbeat:
    """Tests that recover_stale_jobs respects heartbeat timeout."""

    def test_recover_job_with_expired_heartbeat(self, rm_and_queue):
        """Jobs with expired heartbeat should be recovered."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="stale_hb")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            # Heartbeat from 2 minutes ago
            resource.data.last_heartbeat_at = now - dt.timedelta(seconds=120)
            rm.create_or_update(resource_id, resource.data)

        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=30)
        assert resource_id in recovered

        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED

    def test_skip_job_with_recent_heartbeat(self, rm_and_queue):
        """Jobs with recent heartbeat should NOT be recovered (still alive)."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="alive_job")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            # Fresh heartbeat
            resource.data.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
            rm.create_or_update(resource_id, resource.data)

        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=30)
        assert resource_id not in recovered

        # Should still be PROCESSING
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.PROCESSING

    def test_recover_job_with_no_heartbeat(self, rm_and_queue):
        """Jobs with no heartbeat at all (legacy/None) should be recovered."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="legacy_job")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            resource.data.last_heartbeat_at = None
            rm.create_or_update(resource_id, resource.data)

        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=30)
        assert resource_id in recovered

    def test_recover_zero_timeout_recovers_all(self, rm_and_queue):
        """When heartbeat_timeout_seconds=0 is explicitly passed,
        all PROCESSING jobs should be recovered regardless of heartbeat."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="fresh_hb")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            resource.data.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
            rm.create_or_update(resource_id, resource.data)

        # Explicit 0 recovers all PROCESSING jobs (dangerous in multi-worker)
        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)
        assert resource_id in recovered

    def test_recover_is_idempotent_with_heartbeat(self, rm_and_queue):
        """Calling recover multiple times is safe."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="idem")))
            resource = rm.get(info.resource_id)
            resource.data.status = TaskStatus.PROCESSING
            resource.data.last_heartbeat_at = now - dt.timedelta(seconds=120)
            rm.create_or_update(info.resource_id, resource.data)

        recovered1 = queue.recover_stale_jobs(heartbeat_timeout_seconds=30)
        assert len(recovered1) == 1

        recovered2 = queue.recover_stale_jobs(heartbeat_timeout_seconds=30)
        assert len(recovered2) == 0


class TestProcessingAsDraft:
    """Tests that PROCESSING jobs use draft revision for heartbeat compatibility."""

    def test_pop_sets_processing_as_draft(self, rm_and_queue):
        """pop() should set the PROCESSING revision as draft so heartbeat can use modify."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            rm.create(Job(payload=Payload(task_name="draft_pop")))

        job_resource = queue.pop()
        assert job_resource is not None
        assert job_resource.data.status == TaskStatus.PROCESSING

        # The current revision should be in DRAFT status
        with rm.meta_provide(user=user, now=now):
            meta = rm.get_meta(job_resource.info.resource_id)
            rev_info = rm.storage.get_resource_revision_info(
                job_resource.info.resource_id, meta.current_revision_id
            )
            assert rev_info.status == RevisionStatus.draft

    def test_complete_sets_stable_revision(self, rm_and_queue):
        """complete() should create a stable revision (not draft)."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="stable_complete")))
            resource_id = info.resource_id

        job_resource = queue.pop()
        completed = queue.complete(resource_id)

        with rm.meta_provide(user=user, now=now):
            meta = rm.get_meta(resource_id)
            rev_info = rm.storage.get_resource_revision_info(
                resource_id, meta.current_revision_id
            )
            assert rev_info.status == RevisionStatus.stable


class TestPeriodicRecovery:
    """Tests that stale jobs are periodically recovered during consume, not just at startup."""

    def test_periodic_recovery_cleans_stale_job_during_consume(self, rm_and_queue):
        """A stale job created AFTER start_consume should still be recovered."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Set very short recovery interval for testing
        queue._recovery_interval = 0.15
        queue._heartbeat_interval = 0.05

        # Start consumer in background
        consumer_thread = threading.Thread(target=queue.start_consume, daemon=True)
        consumer_thread.start()
        time.sleep(0.1)  # Let consumer start

        # Now create a stale PROCESSING job (simulating another worker dying)
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="mid_consume_stale")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            # Heartbeat expired long ago
            resource.data.last_heartbeat_at = now - dt.timedelta(seconds=300)
            rm.create_or_update(resource_id, resource.data)

        # Wait for periodic recovery to fire
        time.sleep(0.5)
        queue.stop_consuming()
        consumer_thread.join(timeout=2.0)

        # The stale job should have been recovered
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED, (
                f"Expected FAILED but got {res.data.status}. "
                "Periodic recovery should have cleaned this stale job."
            )

    def test_periodic_recovery_does_not_kill_active_jobs(self, rm_and_queue):
        """Periodic recovery should NOT mark jobs with fresh heartbeats as FAILED."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        queue._recovery_interval = 0.15
        queue._heartbeat_interval = 0.05

        consumer_thread = threading.Thread(target=queue.start_consume, daemon=True)
        consumer_thread.start()
        time.sleep(0.1)

        # Create a PROCESSING job and simulate an active heartbeat from another worker
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="active_job")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            resource.data.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
            rm.create_or_update(resource_id, resource.data, status=RevisionStatus.draft)

        # Simulate the other worker's heartbeat keeping the job alive
        fake_hb = HeartbeatThread(
            mq=queue, resource_id=resource_id, interval_seconds=0.05
        )
        fake_hb.start()

        time.sleep(0.5)  # Let periodic recovery fire multiple times

        fake_hb.stop()
        queue.stop_consuming()
        consumer_thread.join(timeout=2.0)

        # Active job should still be PROCESSING
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.PROCESSING, (
                f"Expected PROCESSING but got {res.data.status}. "
                "Periodic recovery should not kill jobs with fresh heartbeats."
            )

    def test_periodic_recovery_stops_when_consuming_stops(self, rm_and_queue):
        """Recovery thread should stop when stop_consuming is called."""
        rm, queue = rm_and_queue
        queue._recovery_interval = 0.05

        consumer_thread = threading.Thread(target=queue.start_consume, daemon=True)
        consumer_thread.start()
        time.sleep(0.1)
        queue.stop_consuming()
        consumer_thread.join(timeout=2.0)

        # No lingering recovery threads
        for t in threading.enumerate():
            assert "recovery" not in t.name.lower(), (
                f"Recovery thread {t.name} still alive after stop_consuming()"
            )
