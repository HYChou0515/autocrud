"""Tests for periodic job functionality in message queues."""

import time
import datetime as dt
from threading import Thread
from msgspec import Struct

from autocrud.message_queue.simple import SimpleMessageQueue
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import Job, Resource, TaskStatus, IndexableField


class SimpleTask(Struct):
    """A simple task payload for testing."""

    name: str
    value: int = 0


def test_simple_periodic_job():
    """Test periodic job with SimpleMessageQueue."""
    # Track execution count
    execution_count = [0]
    results = []

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that increments counter."""
        execution_count[0] += 1
        results.append(
            {
                "run": resource.data.periodic_runs,
                "value": resource.data.payload.value,
                "count": execution_count[0],
            }
        )

    # Create ResourceManager and MessageQueue
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    rm = ResourceManager(
        Job[SimpleTask],
        storage=storage,
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )

    mq = SimpleMessageQueue(do=process_job, resource_manager=rm, max_retries=3)

    # Create a periodic job that runs every 1 second, max 3 times
    job = Job(
        payload=SimpleTask(name="test", value=42),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=3,
    )

    with rm.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm.create(job)

    # Start consumer in background thread
    mq.put(job_info.resource_id)
    consumer_thread = Thread(target=mq.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for periodic job to complete all runs (3 runs * 1 second + buffer)
    time.sleep(5)
    mq.stop_consuming()

    # Verify execution count
    assert execution_count[0] == 3, f"Expected 3 executions, got {execution_count[0]}"

    # Verify periodic_runs increments
    assert len(results) == 3
    assert results[0]["run"] == 0  # First run
    assert results[1]["run"] == 1  # Second run
    assert results[2]["run"] == 2  # Third run

    # Get final job state
    final_resource = rm.get(job_info.resource_id)
    assert final_resource.data.periodic_runs == 3
    assert final_resource.data.status == TaskStatus.COMPLETED


def test_simple_periodic_job_infinite():
    """Test periodic job that runs indefinitely (until manually stopped)."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that increments counter."""
        execution_count[0] += 1

    # Create ResourceManager and MessageQueue
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    rm = ResourceManager(
        Job[SimpleTask],
        storage=storage,
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )

    mq = SimpleMessageQueue(do=process_job, resource_manager=rm, max_retries=3)

    # Create a periodic job with no max_runs (runs forever)
    job = Job(
        payload=SimpleTask(name="infinite_test", value=100),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=None,  # Run indefinitely
    )

    with rm.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm.create(job)

    # Start consumer in background thread
    mq.put(job_info.resource_id)
    consumer_thread = Thread(target=mq.start_consume, daemon=True)
    consumer_thread.start()

    # Let it run for a few seconds
    time.sleep(3.5)
    mq.stop_consuming()

    # Should have run at least 3 times (0s, 1s, 2s, 3s)
    assert execution_count[0] >= 3, (
        f"Expected at least 3 executions, got {execution_count[0]}"
    )

    # Verify job is still in completed state (from last run)
    final_resource = rm.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED
    assert final_resource.data.periodic_runs >= 3


def test_simple_periodic_job_failure_does_not_reschedule():
    """Test that failed periodic jobs do not get rescheduled."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that always fails."""
        execution_count[0] += 1
        raise ValueError("Intentional failure")

    # Create ResourceManager and MessageQueue
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    rm = ResourceManager(
        Job[SimpleTask],
        storage=storage,
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )

    mq = SimpleMessageQueue(do=process_job, resource_manager=rm, max_retries=2)

    # Create a periodic job
    job = Job(
        payload=SimpleTask(name="failure_test", value=99),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=5,
    )

    with rm.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm.create(job)

    # Start consumer in background thread
    mq.put(job_info.resource_id)
    consumer_thread = Thread(target=mq.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for retries to exhaust
    time.sleep(2)
    mq.stop_consuming()

    # Should execute max_retries + 1 times (initial + 2 retries = 3)
    assert execution_count[0] == 3, (
        f"Expected 3 executions (1 initial + 2 retries), got {execution_count[0]}"
    )

    # Verify job failed and was not rescheduled
    final_resource = rm.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.FAILED
    assert final_resource.data.periodic_runs == 0  # Never completed successfully
    assert "Intentional failure" in (final_resource.data.errmsg or "")


def test_non_periodic_job_still_works():
    """Test that non-periodic jobs work as before."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that increments counter."""
        execution_count[0] += 1

    # Create ResourceManager and MessageQueue
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    rm = ResourceManager(
        Job[SimpleTask],
        storage=storage,
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )

    mq = SimpleMessageQueue(do=process_job, resource_manager=rm, max_retries=3)

    # Create a normal (non-periodic) job
    job = Job(
        payload=SimpleTask(name="normal_test", value=123),
        status=TaskStatus.PENDING,
        # No periodic settings
    )

    with rm.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm.create(job)

    # Start consumer in background thread
    mq.put(job_info.resource_id)
    consumer_thread = Thread(target=mq.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for job to complete
    time.sleep(1)
    mq.stop_consuming()

    # Should execute exactly once
    assert execution_count[0] == 1, f"Expected 1 execution, got {execution_count[0]}"

    # Verify job completed
    final_resource = rm.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED
    assert final_resource.data.periodic_runs == 0  # Not a periodic job
