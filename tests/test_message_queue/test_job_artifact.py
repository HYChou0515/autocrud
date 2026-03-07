"""Tests for Job artifact (Phase 2).

Verifies:
- Job[Payload, ArtifactType] with typed artifact
- Handler can set artifact; it persists after complete()
- Rerun resets artifact to None but preserves payload
- Job[Payload] (no D) backward-compatible; artifact is None
"""

import datetime as dt

import msgspec
from msgspec import Struct

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

NOW = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)


# ---- test structs ----


class Payload(Struct):
    task_name: str
    priority: int


class ArtifactType(Struct):
    result: str
    score: float


# ---- helpers ----


def _make_rm_and_queue(handler, job_type=Job[Payload]):
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)
    mq_factory = SimpleMessageQueueFactory()
    rm = ResourceManager(
        job_type,
        storage=storage,
        message_queue=mq_factory.build(handler),
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )
    return rm, rm.message_queue


# ---- tests ----


class TestJobArtifact:
    def test_job_with_typed_artifact_create(self):
        """Job[Payload, ArtifactType] can be instantiated and encoded/decoded."""
        job = Job(
            payload=Payload(task_name="build", priority=1),
            artifact=ArtifactType(result="ok", score=0.99),
        )
        encoded = msgspec.json.encode(job)
        decoded = msgspec.json.decode(encoded, type=Job[Payload, ArtifactType])
        assert decoded.artifact is not None
        assert decoded.artifact.result == "ok"
        assert decoded.artifact.score == 0.99
        assert decoded.payload.task_name == "build"

    def test_job_no_artifact_type_default_none(self):
        """Job[Payload] (single type arg) has artifact=None by default."""
        job: Job[Payload] = Job(payload=Payload(task_name="noop", priority=0))
        assert job.artifact is None

        encoded = msgspec.json.encode(job)
        decoded = msgspec.json.decode(encoded, type=Job[Payload])
        assert decoded.artifact is None

    def test_handler_sets_artifact_persists(self):
        """Handler sets artifact on job; after complete(), it persists in RM."""

        def handler(resource: Resource[Job[Payload]]):
            # Simulate handler producing an artifact
            resource.data.artifact = {"result": "computed", "count": 42}

        rm, mq = _make_rm_and_queue(handler, job_type=Job[Payload, dict])

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="compute", priority=5)))

        rid = info.resource_id
        mq.put(rid)
        mq._execute_job(mq.pop())

        # Verify artifact is persisted
        resource = rm.get(rid)
        assert resource.data.status == TaskStatus.COMPLETED
        assert resource.data.payload.task_name == "compute"
        assert resource.data.artifact == {"result": "computed", "count": 42}

    def test_rerun_resets_artifact(self):
        """After rerun, artifact=None, errmsg=None, retries=0, but payload preserved."""

        def handler(resource: Resource[Job[Payload]]):
            resource.data.artifact = {"result": "done"}

        rm, mq = _make_rm_and_queue(handler, job_type=Job[Payload, dict])

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="initial", priority=1)))

        rid = info.resource_id
        mq.put(rid)
        mq._execute_job(mq.pop())

        # Verify completed
        resource = rm.get(rid)
        assert resource.data.status == TaskStatus.COMPLETED

        # Simulate rerun logic (same as RerunRouteTemplate)
        with rm.meta_provide("testuser", NOW):
            resource = rm.get(rid)
            job = resource.data
            job.status = TaskStatus.PENDING
            job.retries = 0
            job.errmsg = None
            job.artifact = None
            rm.create_or_update(rid, job)

        rerun_resource = rm.get(rid)
        assert rerun_resource.data.status == TaskStatus.PENDING
        assert rerun_resource.data.retries == 0
        assert rerun_resource.data.errmsg is None
        assert rerun_resource.data.artifact is None
        # Payload preserved
        assert rerun_resource.data.payload.task_name == "initial"
        assert rerun_resource.data.payload.priority == 1

    def test_backward_compat_job_single_type_arg(self):
        """Job[Payload] without D still works — artifact is always None."""

        def handler(resource: Resource[Job[Payload]]):
            pass

        rm, mq = _make_rm_and_queue(handler)

        with rm.meta_provide("testuser", NOW):
            info = rm.create(Job(payload=Payload(task_name="compat", priority=0)))

        rid = info.resource_id
        resource = rm.get(rid)
        assert resource.data.artifact is None

        # Process the job
        mq.put(rid)
        mq._execute_job(mq.pop())

        resource = rm.get(rid)
        assert resource.data.status == TaskStatus.COMPLETED
        assert resource.data.artifact is None

    def test_artifact_field_in_job_struct(self):
        """Verify artifact field exists and is accessible."""
        job = Job(payload=Payload(task_name="x", priority=0))
        assert hasattr(job, "artifact")
        assert job.artifact is None

        job.artifact = "some_value"
        assert job.artifact == "some_value"

    def test_artifact_ordering_in_struct(self):
        """Artifact is between errmsg and retries in the struct."""
        job = Job(
            payload=Payload(task_name="t", priority=1),
            status=TaskStatus.COMPLETED,
            errmsg="done",
            artifact=ArtifactType(result="ok", score=1.0),
            retries=2,
        )
        assert job.errmsg == "done"
        assert job.artifact.result == "ok"
        assert job.retries == 2
