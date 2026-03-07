"""Tests for Job logging system (Phase 3).

Verifies:
- JobContext.log() correctly formats log lines
- LogFlushThread periodically flushes to BlobStore
- Lifecycle logs are automatically recorded
- get_logs() reads complete log
- Handler crash only loses logs after the last flush
"""

import datetime as dt
import time
from uuid import uuid4

from msgspec import Struct

from autocrud.message_queue.context import JobContext
from autocrud.message_queue.log_flush import LogFlushThread
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.blob_store.simple import MemoryBlobStore
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

NOW = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


def _rev_info(resource_id: str = "res-1") -> RevisionInfo:
    """Create a minimal RevisionInfo for unit tests."""
    return RevisionInfo(
        uid=uuid4(),
        resource_id=resource_id,
        revision_id="rev-1",
        schema_version=None,
        status=RevisionStatus.stable,
        created_time=NOW,
        updated_time=NOW,
        created_by="test",
        updated_by="test",
    )


class Payload(Struct):
    task_name: str
    priority: int


def _make_rm_and_queue(handler, blob_store=None):
    """Create an RM+MQ pair, optionally with a blob store for log support."""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)
    mq_factory = SimpleMessageQueueFactory()
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        message_queue=mq_factory.build(handler),
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
        blob_store=blob_store,
    )
    return rm, rm.message_queue


# ==========================================================================
# JobContext unit tests
# ==========================================================================


class TestJobContext:
    def _make_ctx(self) -> JobContext:
        """Create a minimal JobContext for unit testing."""
        info = _rev_info("res-1")
        job = Job(payload=Payload(task_name="test", priority=1))
        resource = Resource(info=info, data=job)
        return JobContext(resource)

    def test_log_formats_correctly(self):
        ctx = self._make_ctx()
        ctx.log("hello", "INFO")
        text = ctx.get_log_text()
        assert "[INFO] hello" in text
        # Should contain an ISO-formatted timestamp
        assert "T" in text  # ISO 8601 uses T as separator

    def test_convenience_methods(self):
        ctx = self._make_ctx()
        ctx.info("i")
        ctx.debug("d")
        ctx.warning("w")
        ctx.error("e")
        text = ctx.get_log_text()
        assert "[INFO] i" in text
        assert "[DEBUG] d" in text
        assert "[WARNING] w" in text
        assert "[ERROR] e" in text

    def test_payload_property(self):
        ctx = self._make_ctx()
        assert ctx.payload.task_name == "test"

    def test_set_artifact(self):
        ctx = self._make_ctx()
        ctx.set_artifact({"result": "ok"})
        assert ctx.data.artifact == {"result": "ok"}

    def test_duck_compatible_revision_info_data(self):
        """JobContext exposes .revision_info and .data just like Resource."""
        ctx = self._make_ctx()
        assert ctx.revision_info.resource_id == "res-1"
        assert ctx.data.payload.task_name == "test"

    def test_flush_logs_to_blob_store(self):
        ctx = self._make_ctx()
        ctx.info("line1")
        ctx.error("line2")

        bs = MemoryBlobStore()
        ctx.flush_logs(bs, "test-key")

        blob = bs.get("test-key")
        text = blob.data.decode("utf-8")
        assert "[INFO] line1" in text
        assert "[ERROR] line2" in text

    def test_flush_logs_empty_buffer_no_write(self):
        """Empty buffer should not write to blob store."""
        ctx = self._make_ctx()
        bs = MemoryBlobStore()
        ctx.flush_logs(bs, "empty-key")
        assert not bs.exists("empty-key")


# ==========================================================================
# LogFlushThread tests
# ==========================================================================


class TestLogFlushThread:
    def test_periodic_flush(self):
        """LogFlushThread flushes logs periodically."""
        info = _rev_info("res-2")
        job = Job(payload=Payload(task_name="flush-test", priority=1))
        resource = Resource(info=info, data=job)
        ctx = JobContext(resource)
        bs = MemoryBlobStore()

        ctx.info("before-start")

        lf = LogFlushThread(ctx=ctx, blob_store=bs, key="lf-test", interval_seconds=0.1)
        lf.start()

        # Wait enough time for at least one flush cycle
        time.sleep(0.3)

        # Add more logs while thread is running
        ctx.info("during-run")

        lf.stop()  # Stop does a final flush

        blob = bs.get("lf-test")
        text = blob.data.decode("utf-8")
        assert "[INFO] before-start" in text
        assert "[INFO] during-run" in text

    def test_stop_does_final_flush(self):
        """stop() performs a final flush after signalling the thread."""
        info = _rev_info("res-3")
        job = Job(payload=Payload(task_name="final-flush", priority=1))
        resource = Resource(info=info, data=job)
        ctx = JobContext(resource)
        bs = MemoryBlobStore()

        lf = LogFlushThread(
            ctx=ctx, blob_store=bs, key="final-test", interval_seconds=100
        )
        lf.start()

        # Write log, but interval is very long — won't flush on its own
        ctx.info("only-after-stop")

        lf.stop()

        blob = bs.get("final-test")
        text = blob.data.decode("utf-8")
        assert "[INFO] only-after-stop" in text


# ==========================================================================
# Integration: lifecycle logs via _execute_job
# ==========================================================================


class TestJobLifecycleLogs:
    def test_lifecycle_logs_auto_recorded(self):
        """Framework auto-records 'Job started' and 'Job completed'."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]]):
            pass  # No-op handler

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="lifecycle", priority=1)))

        rid = info.resource_id
        mq.put(rid)
        mq._execute_job(mq.pop())

        logs = mq.get_logs(rid)
        assert logs is not None
        assert "Job started" in logs
        assert "Job completed" in logs

    def test_lifecycle_logs_on_failure(self):
        """Failed job records error log."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]]):
            raise ValueError("boom!")

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)
        # Set max_retries=0 so it fails immediately
        mq.max_retries = 0

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="fail", priority=1)))

        rid = info.resource_id
        mq.put(rid)
        mq._execute_job(mq.pop())

        logs = mq.get_logs(rid)
        assert logs is not None
        assert "Job started" in logs
        assert "Job failed" in logs
        assert "boom!" in logs

    def test_get_logs_returns_none_without_blob_store(self):
        """get_logs() returns None when no blob store is configured."""

        def handler(resource: Resource[Job[Payload]]):
            pass

        rm, mq = _make_rm_and_queue(handler, blob_store=None)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="no-bs", priority=1)))

        rid = info.resource_id
        assert mq.get_logs(rid) is None

    def test_get_logs_returns_none_for_never_executed(self):
        """get_logs() returns None for a job that was never executed."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]]):
            pass

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="never", priority=1)))

        assert mq.get_logs(info.resource_id) is None

    def test_rerun_overwrites_log(self):
        """Rerun executes again and overwrites the log for the same key."""
        bs = MemoryBlobStore()
        call_count = [0]

        def handler(resource: Resource[Job[Payload]]):
            call_count[0] += 1

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="rerun-log", priority=1)))

        rid = info.resource_id

        # First run
        mq.put(rid)
        mq._execute_job(mq.pop())
        logs_v1 = mq.get_logs(rid)
        assert "Job started" in logs_v1
        assert call_count[0] == 1

        # Simulate rerun
        with rm.meta_provide("testuser", NOW):
            resource = rm.get(rid)
            job = resource.data
            job.status = TaskStatus.PENDING
            job.retries = 0
            job.errmsg = None
            job.artifact = None
            rm.create_or_update(rid, job)

        mq.put(rid)
        mq._execute_job(mq.pop())
        logs_v2 = mq.get_logs(rid)
        assert "Job started" in logs_v2
        assert call_count[0] == 2
        # The log is overwritten (new execution), so it's a fresh log

    def test_handler_crash_loses_only_unflushed_logs(self):
        """Handler crash mid-execution: final flush captures what was logged."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]]):
            # The framework logs "Job started" before handler runs
            raise RuntimeError("crash mid-work")

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)
        mq.max_retries = 0

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="crash", priority=1)))

        rid = info.resource_id
        mq.put(rid)
        mq._execute_job(mq.pop())

        logs = mq.get_logs(rid)
        assert logs is not None
        # "Job started" should be present (logged before handler)
        assert "Job started" in logs
        # "Job failed" should also be present (logged in exception handler)
        assert "Job failed" in logs
