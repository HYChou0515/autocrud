"""Tests for JobContext injection into handlers.

Verifies that:
- Old-style handler ``def handler(resource)`` works without changes.
- New-style handler ``def handler(resource, job_context=None)`` receives
  the ``JobContext`` automatically.
- Handler can use ``job_context`` to log and set artifacts.
- ``_check_handler_wants_context`` correctly detects the parameter.
- Handler with job_context but NO blobstore still gets a working ctx + warning.
- JobContext.log() also emits to Python logging.
"""

import datetime as dt
import logging
import warnings

from msgspec import Struct

from autocrud.message_queue.basic import BasicMessageQueue
from autocrud.message_queue.context import JobContext
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.blob_store.simple import MemoryBlobStore
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import (
    IndexableField,
    Job,
    Resource,
    TaskStatus,
)

NOW = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


class Payload(Struct):
    task_name: str
    priority: int


def _make_rm_and_queue(handler, blob_store=None):
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
# _check_handler_wants_context unit tests
# ==========================================================================


class TestCheckHandlerWantsContext:
    """Unit tests for the handler introspection logic."""

    def test_old_style_handler_no_context(self):
        """Handler(resource) → False."""

        def handler(resource):
            pass

        assert BasicMessageQueue._check_handler_wants_context(handler) is False

    def test_new_style_handler_with_context(self):
        """Handler(resource, job_context=None) → True."""

        def handler(resource, job_context=None):
            pass

        assert BasicMessageQueue._check_handler_wants_context(handler) is True

    def test_new_style_handler_with_typed_context(self):
        """Handler(resource, job_context: JobContext) → True."""

        def handler(resource: Resource[Job], job_context: JobContext = None):
            pass

        assert BasicMessageQueue._check_handler_wants_context(handler) is True

    def test_handler_with_other_kwargs(self):
        """Handler(resource, foo=1) → False (no job_context param)."""

        def handler(resource, foo=1):
            pass

        assert BasicMessageQueue._check_handler_wants_context(handler) is False

    def test_lambda_handler(self):
        """Lambda handler → False."""
        handler = lambda resource: None  # noqa: E731
        assert BasicMessageQueue._check_handler_wants_context(handler) is False

    def test_callable_class_handler(self):
        """Callable class with __call__(self, resource, job_context) → True."""

        class Handler:
            def __call__(self, resource, job_context=None):
                pass

        assert BasicMessageQueue._check_handler_wants_context(Handler()) is True


# ==========================================================================
# Integration: old-style handler (backward compat)
# ==========================================================================


class TestOldStyleHandler:
    def test_old_handler_works_unchanged(self):
        """Old handler(resource) still works without receiving job_context."""
        results = []

        def handler(resource: Resource[Job[Payload]]):
            results.append(resource.data.payload.task_name)

        rm, mq = _make_rm_and_queue(handler)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="old-style", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        assert results == ["old-style"]
        resource = rm.get(info.resource_id)
        assert resource.data.status == TaskStatus.COMPLETED

    def test_old_handler_with_blob_store_logs_lifecycle(self):
        """Old handler still gets lifecycle logs even without job_context."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]]):
            pass

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="old-bs", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        logs = mq.get_logs(info.resource_id)
        assert "Job started" in logs
        assert "Job completed" in logs


# ==========================================================================
# Integration: new-style handler (with job_context)
# ==========================================================================


class TestNewStyleHandler:
    def test_handler_receives_job_context(self):
        """Handler with job_context parameter receives the JobContext."""
        received_ctx = []

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            received_ctx.append(job_context)

        rm, mq = _make_rm_and_queue(handler)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="ctx-test", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        assert len(received_ctx) == 1
        ctx = received_ctx[0]
        assert isinstance(ctx, JobContext)
        assert ctx.data.payload.task_name == "ctx-test"

    def test_handler_logs_via_context(self):
        """Handler can log via job_context and logs appear in get_logs()."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            job_context.info("Handler says hello")
            job_context.debug("Debug detail")

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="log-ctx", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        logs = mq.get_logs(info.resource_id)
        assert "Handler says hello" in logs
        assert "Debug detail" in logs
        # Framework lifecycle logs are also present
        assert "Job started" in logs
        assert "Job completed" in logs

    def test_handler_sets_artifact_via_context(self):
        """Handler can set artifact via job_context.set_artifact()."""

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            job_context.set_artifact({"score": 99})

        rm, mq = _make_rm_and_queue(handler)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="art-ctx", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        resource = rm.get(info.resource_id)
        assert resource.data.status == TaskStatus.COMPLETED

    def test_handler_error_still_logs(self):
        """Handler with job_context that raises still gets error in logs."""
        bs = MemoryBlobStore()

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            job_context.info("Before crash")
            raise ValueError("oops")

        rm, mq = _make_rm_and_queue(handler, blob_store=bs)
        mq.max_retries = 0

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="err-ctx", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        logs = mq.get_logs(info.resource_id)
        assert "Before crash" in logs
        assert "Job failed" in logs
        assert "oops" in logs


# ==========================================================================
# No blobstore: handler still gets a working ctx + warning
# ==========================================================================


class TestNoBlobStoreWithJobContext:
    def test_handler_gets_ctx_without_blobstore(self):
        """Handler with job_context but NO blobstore still gets a real ctx."""
        received_ctx = []

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            # Must be a real JobContext, not None
            assert job_context is not None
            job_context.info("I can log without blob store")
            received_ctx.append(job_context)

        rm, mq = _make_rm_and_queue(handler, blob_store=None)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="no-bs-ctx", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        assert len(received_ctx) == 1
        assert isinstance(received_ctx[0], JobContext)
        resource = rm.get(info.resource_id)
        assert resource.data.status == TaskStatus.COMPLETED

    def test_handler_set_artifact_without_blobstore(self):
        """set_artifact() works even without blobstore."""

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            job_context.set_artifact({"x": 1})

        rm, mq = _make_rm_and_queue(handler, blob_store=None)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="art-nobs", priority=1)))

        mq.put(info.resource_id)
        mq._execute_job(mq.pop())

        resource = rm.get(info.resource_id)
        assert resource.data.status == TaskStatus.COMPLETED

    def test_fallback_ctx_when_invoke_handler_gets_none(self):
        """_invoke_handler creates fallback ctx + emits warning if ctx=None."""
        received_ctx = []

        def handler(resource: Resource[Job[Payload]], job_context: JobContext = None):
            received_ctx.append(job_context)

        rm, mq = _make_rm_and_queue(handler, blob_store=None)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="fallback", priority=1)))

        resource = rm.get(info.resource_id)
        # Directly call _invoke_handler with ctx=None to trigger the fallback
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            mq._invoke_handler(resource, ctx=None)

        assert len(received_ctx) == 1
        assert isinstance(received_ctx[0], JobContext)
        # A warning should have been emitted
        assert any("job_context" in str(warning.message).lower() for warning in w)


# ==========================================================================
# Python logging integration
# ==========================================================================


class TestJobContextLogging:
    def test_log_emits_to_python_logger(self, caplog):
        """ctx.log() should also emit to Python's logging module."""
        from uuid import uuid4

        from autocrud.types import RevisionInfo, RevisionStatus

        rev_info = RevisionInfo(
            uid=uuid4(),
            resource_id="log-test-1",
            revision_id="rev-1",
            schema_version=None,
            status=RevisionStatus.stable,
            created_time=NOW,
            updated_time=NOW,
            created_by="test",
            updated_by="test",
        )
        job = Job(payload=Payload(task_name="logger", priority=1))
        resource = Resource(info=rev_info, data=job)
        ctx = JobContext(resource)

        with caplog.at_level(logging.DEBUG, logger="autocrud.job"):
            ctx.info("hello from handler")
            ctx.debug("debug detail")
            ctx.warning("be careful")
            ctx.error("something broke")

        messages = [r.message for r in caplog.records]
        assert any("hello from handler" in m for m in messages)
        assert any("debug detail" in m for m in messages)
        assert any("be careful" in m for m in messages)
        assert any("something broke" in m for m in messages)

    def test_log_includes_resource_id_in_logger(self, caplog):
        """Logger output should include the resource_id for traceability."""
        from uuid import uuid4

        from autocrud.types import RevisionInfo, RevisionStatus

        rev_info = RevisionInfo(
            uid=uuid4(),
            resource_id="my-job-42",
            revision_id="rev-1",
            schema_version=None,
            status=RevisionStatus.stable,
            created_time=NOW,
            updated_time=NOW,
            created_by="test",
            updated_by="test",
        )
        job = Job(payload=Payload(task_name="logger", priority=1))
        resource = Resource(info=rev_info, data=job)
        ctx = JobContext(resource)

        with caplog.at_level(logging.DEBUG, logger="autocrud.job"):
            ctx.info("test msg")

        assert any("my-job-42" in r.message for r in caplog.records)

    def test_log_level_mapping(self, caplog):
        """Each convenience method maps to the correct Python log level."""
        from uuid import uuid4

        from autocrud.types import RevisionInfo, RevisionStatus

        rev_info = RevisionInfo(
            uid=uuid4(),
            resource_id="lvl-test",
            revision_id="rev-1",
            schema_version=None,
            status=RevisionStatus.stable,
            created_time=NOW,
            updated_time=NOW,
            created_by="test",
            updated_by="test",
        )
        job = Job(payload=Payload(task_name="levels", priority=1))
        resource = Resource(info=rev_info, data=job)
        ctx = JobContext(resource)

        with caplog.at_level(logging.DEBUG, logger="autocrud.job"):
            ctx.info("i")
            ctx.debug("d")
            ctx.warning("w")
            ctx.error("e")

        levels = {r.levelname for r in caplog.records}
        assert "INFO" in levels
        assert "DEBUG" in levels
        assert "WARNING" in levels
        assert "ERROR" in levels
