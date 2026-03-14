"""
Tests for HeartbeatThread integration in CeleryMessageQueue.

Verifies that CeleryMessageQueue:
1. Uses RevisionStatus.draft when setting PROCESSING (so modify() works)
2. Starts/stops HeartbeatThread during job execution
3. last_heartbeat_at is updated during long-running jobs

Follow TDD: these tests are written BEFORE the implementation.
"""

from __future__ import annotations

import datetime as dt
import time

import pytest
from msgspec import Struct

from autocrud.message_queue.celery_queue import (
    CeleryMessageQueue,
)
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import Job, Resource, RevisionStatus, TaskStatus


class SlowTask(Struct):
    """Task data for heartbeat tests."""

    duration: float = 0.0


@pytest.fixture
def celery_app():
    """Create a test Celery app (eager mode)."""
    try:
        from celery import Celery
    except ImportError:
        pytest.skip("celery not installed")

    app = Celery("test_hb_app", broker="memory://", backend="cache+memory://")
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache+memory://",
    )
    return app


@pytest.fixture
def resource_manager():
    """Create a test ResourceManager."""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store=meta_store, resource_store=resource_store)
    return ResourceManager(
        Job[SlowTask],
        storage=storage,
        default_user="system",
        default_now=lambda: dt.datetime.now(),
    )


class TestCeleryHeartbeat:
    """Verify HeartbeatThread integration in CeleryMessageQueue."""

    def test_processing_uses_draft_revision(self, celery_app, resource_manager):
        """When a job is set to PROCESSING, the revision must be draft
        so that HeartbeatThread's rm.modify() can update last_heartbeat_at.

        This is consistent with SimpleMessageQueue.pop() behaviour.
        """
        captured_status: list[RevisionStatus] = []

        def capture_callback(resource: Resource[Job[SlowTask]]):
            # During execution, check the revision status
            rid = resource.info.resource_id
            meta = resource_manager.get_meta(rid)
            rev_info = resource_manager.storage.get_resource_revision_info(
                rid, meta.current_revision_id
            )
            captured_status.append(rev_info.status)

        queue = CeleryMessageQueue(
            do=capture_callback,
            resource_manager=resource_manager,
            celery_app=celery_app,
        )

        with resource_manager.meta_provide(user="test_user"):
            job = resource_manager.create(Job(payload=SlowTask()))
            queue.put(job.resource_id)

        assert len(captured_status) == 1
        assert captured_status[0] == RevisionStatus.draft, (
            "PROCESSING revision should be draft so HeartbeatThread modify() works"
        )

    def test_heartbeat_updates_last_heartbeat_at(self, celery_app, resource_manager):
        """A job running longer than the heartbeat interval should have
        last_heartbeat_at set by HeartbeatThread.
        """
        heartbeat_values: list[dt.datetime | None] = []

        def slow_callback(resource: Resource[Job[SlowTask]]):
            # Sleep long enough for at least one heartbeat tick
            time.sleep(2.5)
            # Check last_heartbeat_at while still executing
            rid = resource.info.resource_id
            res = resource_manager.get(rid)
            heartbeat_values.append(res.data.last_heartbeat_at)

        queue = CeleryMessageQueue(
            do=slow_callback,
            resource_manager=resource_manager,
            celery_app=celery_app,
        )
        queue._heartbeat_interval = 1.0  # tick every 1s

        with resource_manager.meta_provide(user="test_user"):
            job = resource_manager.create(Job(payload=SlowTask(duration=2.5)))
            queue.put(job.resource_id)

        assert len(heartbeat_values) == 1
        assert heartbeat_values[0] is not None, (
            "HeartbeatThread should have updated last_heartbeat_at during execution"
        )

    def test_heartbeat_stopped_after_completion(self, celery_app, resource_manager):
        """HeartbeatThread must be stopped after job completes (no resource leak)."""
        hb_threads: list = []

        original_register = CeleryMessageQueue._register_task

        def patched_do(resource: Resource[Job[SlowTask]]):
            time.sleep(1.5)

        queue = CeleryMessageQueue(
            do=patched_do,
            resource_manager=resource_manager,
            celery_app=celery_app,
        )
        queue._heartbeat_interval = 0.5

        # Monkey-patch to capture HeartbeatThread instances
        from unittest.mock import patch

        orig_hb_init = None
        try:
            from autocrud.message_queue.heartbeat import HeartbeatThread

            orig_start = HeartbeatThread.start

            def tracking_start(self):
                hb_threads.append(self)
                return orig_start(self)

            with patch.object(HeartbeatThread, "start", tracking_start):
                with resource_manager.meta_provide(user="test_user"):
                    job = resource_manager.create(Job(payload=SlowTask()))
                    queue.put(job.resource_id)
        except ImportError:
            pytest.skip("HeartbeatThread not available")

        assert len(hb_threads) >= 1, "HeartbeatThread should have been started"
        for hb in hb_threads:
            assert hb._stop_event.is_set(), "HeartbeatThread should be stopped"

    def test_failed_job_still_has_heartbeat(self, celery_app, resource_manager):
        """Even when a job fails, last_heartbeat_at should have been updated
        during execution (before the failure).
        """

        def failing_slow_callback(resource: Resource[Job[SlowTask]]):
            time.sleep(2.5)
            raise RuntimeError("boom")

        queue = CeleryMessageQueue(
            do=failing_slow_callback,
            resource_manager=resource_manager,
            celery_app=celery_app,
            max_retries=0,
        )
        queue._heartbeat_interval = 1.0

        with resource_manager.meta_provide(user="test_user"):
            job = resource_manager.create(Job(payload=SlowTask()))
            queue.put(job.resource_id)

        res = resource_manager.get(job.resource_id)
        assert res.data.status == TaskStatus.FAILED
        assert res.data.last_heartbeat_at is not None, (
            "HeartbeatThread should have ticked before the job failed"
        )
