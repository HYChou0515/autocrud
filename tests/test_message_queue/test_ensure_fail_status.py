"""Tests ensuring job status is ALWAYS set to FAILED when job execution fails.

These tests verify that even when internal operations (like create_or_update) fail
during error handling, the job status is still reliably set to FAILED.
Also tests stale job recovery for jobs stuck in PROCESSING (e.g. after OOM kill).
"""

import datetime as dt
import threading
import time
from unittest.mock import patch

import pytest
from msgspec import Struct

from autocrud.message_queue.basic import NoRetry
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import (
    IndexableField,
    Job,
    Resource,
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


class TestEnsureFailStatusOnJobFail:
    """Ensure job status is set to FAILED whenever job execution fails."""

    def test_execute_job_sets_failed_when_create_or_update_fails_no_retry(
        self, rm_and_queue
    ):
        """When _do raises, should_retry=False, and create_or_update also fails,
        the job status MUST still end up as FAILED."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="test_job")))
            resource_id = info.resource_id

        # Pop and set to PROCESSING
        job_resource = queue.pop()
        assert job_resource is not None
        assert job_resource.data.status == TaskStatus.PROCESSING

        # Make the callback fail with NoRetry (so should_retry=False)
        queue._do = lambda r: (_ for _ in ()).throw(NoRetry("fatal error"))

        # Make the first create_or_update in error handler fail
        original_create_or_update = rm.create_or_update
        call_count = [0]

        def flaky_create_or_update(rid, data):
            call_count[0] += 1
            # Fail on the first call (the primary error-handling update)
            if call_count[0] == 1:
                raise RuntimeError("Storage temporarily unavailable")
            return original_create_or_update(rid, data)

        with patch.object(rm, "create_or_update", side_effect=flaky_create_or_update):
            queue._execute_job(job_resource)

        # The job MUST be FAILED, not stuck in PROCESSING
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED, (
                f"Expected FAILED but got {res.data.status}. "
                "Job status should be FAILED even when create_or_update fails."
            )

    def test_execute_job_sets_failed_when_create_or_update_fails_with_retry(
        self, rm_and_queue
    ):
        """When _do raises a retryable error but the first create_or_update fails,
        the fallback should set FAILED instead of leaving the job stuck in PROCESSING."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="retry_job")))
            resource_id = info.resource_id

        # Pop and set to PROCESSING
        job_resource = queue.pop()
        assert job_resource is not None

        # Make the callback fail (retryable error, retries=1 <= max_retries=3)
        queue._do = lambda r: (_ for _ in ()).throw(ValueError("transient error"))

        # Make the first create_or_update fail (setting PENDING),
        # but allow subsequent calls (fallback fail()) to succeed
        original_create_or_update = rm.create_or_update
        call_count = [0]

        def flaky_create_or_update(rid, data):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("Storage temporarily unavailable")
            return original_create_or_update(rid, data)

        with patch.object(rm, "create_or_update", side_effect=flaky_create_or_update):
            queue._execute_job(job_resource)

        # The fallback should have set FAILED (not stuck in PROCESSING)
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED, (
                f"Expected FAILED but got {res.data.status}. "
                "Job should be FAILED when retry update fails and fallback succeeds."
            )

    def test_start_consume_does_not_crash_on_execute_job_failure(self, rm_and_queue):
        """start_consume should not crash when _execute_job encounters
        an unhandled exception. The consumer loop must continue running."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create two jobs
        with rm.meta_provide(user=user, now=now):
            info1 = rm.create(Job(payload=Payload(task_name="crashing_job")))
            info2 = rm.create(Job(payload=Payload(task_name="normal_job")))
            resource_id1 = info1.resource_id
            resource_id2 = info2.resource_id

        processed_jobs = []

        call_count = [0]

        def worker_logic(resource: Resource[Job[Payload]]):
            call_count[0] += 1
            task_name = resource.data.payload.task_name
            processed_jobs.append(task_name)
            if task_name == "crashing_job":
                raise ValueError("Job crashed!")
            # normal_job succeeds

        queue._do = worker_logic

        # Run consumer in a thread with a short timeout
        def run_consumer():
            queue.start_consume()

        consumer_thread = threading.Thread(target=run_consumer, daemon=True)
        consumer_thread.start()

        # Wait for both jobs to be processed
        time.sleep(1.0)
        queue.stop_consuming()
        consumer_thread.join(timeout=2.0)

        # Both jobs should have been processed (consumer didn't crash after first failure)
        assert "crashing_job" in processed_jobs, "First job should have been processed"
        assert "normal_job" in processed_jobs, (
            "Second job should have been processed (consumer should not crash)"
        )

        # First job should be FAILED
        with rm.meta_provide(user=user, now=now):
            res1 = rm.get(resource_id1)
            assert res1.data.status == TaskStatus.FAILED

    def test_execute_job_all_updates_fail_does_not_raise(self, rm_and_queue):
        """When _do raises AND all attempts to update status fail,
        _execute_job should still not raise (to protect caller loop)."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="all_fail_job")))

        # Pop
        job_resource = queue.pop()

        # Make callback fail
        queue._do = lambda r: (_ for _ in ()).throw(NoRetry("fatal"))

        # Make ALL RM operations fail
        def always_fail(*args, **kwargs):
            raise RuntimeError("Complete storage failure")

        with patch.object(rm, "create_or_update", side_effect=always_fail):
            with patch.object(rm, "get", side_effect=always_fail):
                # This should NOT raise, even if all updates fail
                queue._execute_job(job_resource)

    def test_execute_job_fail_called_even_on_primary_update_success(self, rm_and_queue):
        """When _do raises and create_or_update succeeds,
        fail() should also be called for non-retryable errors."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="fail_test")))
            resource_id = info.resource_id

        job_resource = queue.pop()
        queue._do = lambda r: (_ for _ in ()).throw(NoRetry("no retry"))

        queue._execute_job(job_resource)

        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            assert "no retry" in res.data.errmsg


class TestRecoverStaleJobs:
    """Tests for recovering jobs stuck in PROCESSING after worker crash (e.g. OOM kill)."""

    def test_recover_stale_jobs_marks_processing_as_failed(self, rm_and_queue):
        """Jobs stuck in PROCESSING should be marked as FAILED by recover_stale_jobs."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a job and manually set it to PROCESSING (simulating a killed worker)
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="stuck_job")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(resource_id, resource.data)

        # Verify it's PROCESSING
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.PROCESSING

        # Recover stale jobs
        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)

        # Should have recovered 1 job
        assert len(recovered) == 1
        assert recovered[0] == resource_id

        # Job should now be FAILED
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED
            assert res.data.errmsg is not None
            assert (
                "stale" in res.data.errmsg.lower()
                or "recover" in res.data.errmsg.lower()
            )

    def test_recover_stale_jobs_does_not_affect_other_statuses(self, rm_and_queue):
        """Jobs in PENDING, COMPLETED, FAILED should NOT be affected by recovery."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            # PENDING job
            info_pending = rm.create(Job(payload=Payload(task_name="pending_job")))
            # COMPLETED job
            info_completed = rm.create(Job(payload=Payload(task_name="completed_job")))
            res_completed = rm.get(info_completed.resource_id)
            res_completed.data.status = TaskStatus.COMPLETED
            rm.create_or_update(info_completed.resource_id, res_completed.data)
            # FAILED job
            info_failed = rm.create(Job(payload=Payload(task_name="failed_job")))
            res_failed = rm.get(info_failed.resource_id)
            res_failed.data.status = TaskStatus.FAILED
            res_failed.data.errmsg = "previously failed"
            rm.create_or_update(info_failed.resource_id, res_failed.data)

        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)
        assert len(recovered) == 0

        # Verify statuses unchanged
        with rm.meta_provide(user=user, now=now):
            assert rm.get(info_pending.resource_id).data.status == TaskStatus.PENDING
            assert (
                rm.get(info_completed.resource_id).data.status == TaskStatus.COMPLETED
            )
            assert rm.get(info_failed.resource_id).data.status == TaskStatus.FAILED

    def test_recover_stale_jobs_multiple_processing(self, rm_and_queue):
        """Multiple stuck PROCESSING jobs should all be recovered."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        resource_ids = []
        with rm.meta_provide(user=user, now=now):
            for i in range(3):
                info = rm.create(Job(payload=Payload(task_name=f"stuck_{i}")))
                resource = rm.get(info.resource_id)
                resource.data.status = TaskStatus.PROCESSING
                rm.create_or_update(info.resource_id, resource.data)
                resource_ids.append(info.resource_id)

        recovered = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)
        assert len(recovered) == 3

        for rid in resource_ids:
            with rm.meta_provide(user=user, now=now):
                res = rm.get(rid)
                assert res.data.status == TaskStatus.FAILED

    def test_start_consume_calls_recover_stale_jobs(self, rm_and_queue):
        """start_consume should automatically recover stale jobs before processing new ones."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        # Create a stuck PROCESSING job (simulating previous worker crash)
        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="orphaned_job")))
            resource_id = info.resource_id
            resource = rm.get(resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(resource_id, resource.data)

        # Start the consumer briefly
        queue._do = lambda r: None  # no-op handler
        consumer_thread = threading.Thread(target=queue.start_consume, daemon=True)
        consumer_thread.start()
        time.sleep(0.5)
        queue.stop_consuming()
        consumer_thread.join(timeout=2.0)

        # The stuck job should have been recovered to FAILED
        with rm.meta_provide(user=user, now=now):
            res = rm.get(resource_id)
            assert res.data.status == TaskStatus.FAILED, (
                f"Expected FAILED but got {res.data.status}. "
                "start_consume should recover stale PROCESSING jobs."
            )

    def test_recover_stale_jobs_is_idempotent(self, rm_and_queue):
        """Calling recover_stale_jobs multiple times should be safe."""
        rm, queue = rm_and_queue
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            info = rm.create(Job(payload=Payload(task_name="stuck_job")))
            resource = rm.get(info.resource_id)
            resource.data.status = TaskStatus.PROCESSING
            rm.create_or_update(info.resource_id, resource.data)

        # First recovery
        recovered1 = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)
        assert len(recovered1) == 1

        # Second recovery - no more stale jobs
        recovered2 = queue.recover_stale_jobs(heartbeat_timeout_seconds=0)
        assert len(recovered2) == 0

        # Status should still be FAILED
        with rm.meta_provide(user=user, now=now):
            res = rm.get(info.resource_id)
            assert res.data.status == TaskStatus.FAILED
