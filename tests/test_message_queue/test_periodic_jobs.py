"""Tests for periodic job functionality in message queues."""

import datetime as dt
import time
from threading import Thread
from unittest.mock import MagicMock

import pytest
from msgspec import Struct

from autocrud.message_queue.rabbitmq import RabbitMQMessageQueue
from autocrud.message_queue.simple import SimpleMessageQueue
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import IndexableField, Job, Resource, TaskStatus

# Check if pika is available
try:
    import pika  # noqa: F401

    PIKA_AVAILABLE = True
except ImportError:
    PIKA_AVAILABLE = False


class SimpleTask(Struct):
    """A simple task payload for testing."""

    name: str
    value: int = 0


@pytest.fixture
def rm_fixture():
    """Create a ResourceManager for testing."""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)

    rm = ResourceManager(
        Job[SimpleTask],
        storage=storage,
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )
    return rm


@pytest.fixture(
    params=[
        pytest.param("simple", id="simple"),
        pytest.param(
            "rabbitmq",
            marks=pytest.mark.skipif(not PIKA_AVAILABLE, reason="pika not installed"),
            id="rabbitmq",
        ),
    ]
)
def mq_fixture(request, rm_fixture):
    """Create a message queue (SimpleMessageQueue or RabbitMQMessageQueue)."""
    queue_type = request.param

    # Placeholder handler (will be replaced in tests)
    def dummy_handler(resource):
        pass

    if queue_type == "simple":
        mq = SimpleMessageQueue(
            do=dummy_handler, resource_manager=rm_fixture, max_retries=3
        )
    else:  # rabbitmq
        # Use unique queue prefix for each test to avoid queue parameter conflicts
        import uuid

        unique_prefix = f"test-{uuid.uuid4().hex[:8]}:"
        mq = RabbitMQMessageQueue(
            do=dummy_handler,
            resource_manager=rm_fixture,
            queue_prefix=unique_prefix,
            max_retries=3,
            retry_delay_seconds=1,  # Use 1 second for faster tests
        )

    yield mq

    # Cleanup
    if hasattr(mq, "stop_consuming"):
        mq.stop_consuming()

    # Delete RabbitMQ queues after test
    if queue_type == "rabbitmq":
        with mq._get_connection() as (_, channel):
            for queue_name in [
                mq.queue_name,
                f"{mq.queue_name}:retry",
                f"{mq.queue_name}:dead",
            ]:
                try:
                    channel.queue_delete(queue=queue_name)
                except Exception:
                    pass  # Ignore errors during cleanup


def test_periodic_job_basic(mq_fixture, rm_fixture):
    """Test periodic job runs specified number of times."""
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

    # Replace handler
    mq_fixture._do = process_job

    # Create a periodic job that runs every 1 second, max 3 times
    job = Job(
        payload=SimpleTask(name="test", value=42),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=3,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer in background thread
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for periodic job to complete all runs (3 runs * 1 second + buffer)
    time.sleep(5)
    mq_fixture.stop_consuming()

    # Verify execution count
    assert execution_count[0] == 3, f"Expected 3 executions, got {execution_count[0]}"

    # Verify periodic_runs increments
    assert len(results) == 3
    assert results[0]["run"] == 0  # First run
    assert results[1]["run"] == 1  # Second run
    assert results[2]["run"] == 2  # Third run

    # Get final job state
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.periodic_runs == 3
    assert final_resource.data.status == TaskStatus.COMPLETED


def test_periodic_job_infinite(mq_fixture, rm_fixture):
    """Test periodic job that runs indefinitely (until manually stopped)."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that increments counter."""
        execution_count[0] += 1

    # Replace handler
    mq_fixture._do = process_job

    # Create a periodic job with no max_runs (runs forever)
    job = Job(
        payload=SimpleTask(name="infinite_test", value=100),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=None,  # Run indefinitely
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer in background thread
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Let it run for a few seconds
    time.sleep(3.5)
    mq_fixture.stop_consuming()

    # Should have run at least 3 times (0s, 1s, 2s, 3s)
    assert execution_count[0] >= 3, (
        f"Expected at least 3 executions, got {execution_count[0]}"
    )

    # Verify job is still in completed state (from last run)
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED
    assert final_resource.data.periodic_runs >= 3


def test_periodic_job_failure_does_not_reschedule(mq_fixture, rm_fixture):
    """Test that failed periodic jobs do not get rescheduled."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that always fails."""
        execution_count[0] += 1
        raise ValueError("Intentional failure")

    # Replace handler and max_retries
    mq_fixture._do = process_job
    mq_fixture.max_retries = 2

    # Create a periodic job
    job = Job(
        payload=SimpleTask(name="failure_test", value=99),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=5,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer in background thread
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for retries to exhaust (RabbitMQ needs time for retry delays)
    time.sleep(5)
    mq_fixture.stop_consuming()

    # Should execute max_retries + 1 times (initial + 2 retries = 3)
    assert execution_count[0] == 3, (
        f"Expected 3 executions (1 initial + 2 retries), got {execution_count[0]}"
    )

    # Verify job failed and was not rescheduled
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.FAILED
    assert final_resource.data.periodic_runs == 0  # Never completed successfully
    assert "Intentional failure" in (final_resource.data.errmsg or "")


def test_non_periodic_job_still_works(mq_fixture, rm_fixture):
    """Test that non-periodic jobs work as before."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that increments counter."""
        execution_count[0] += 1

    # Replace handler
    mq_fixture._do = process_job

    # Create a normal (non-periodic) job
    job = Job(
        payload=SimpleTask(name="normal_test", value=123),
        status=TaskStatus.PENDING,
        # No periodic settings
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer in background thread
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for job to complete
    time.sleep(1)
    mq_fixture.stop_consuming()

    # Should execute exactly once
    assert execution_count[0] == 1, f"Expected 1 execution, got {execution_count[0]}"

    # Verify job completed
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED
    assert final_resource.data.periodic_runs == 0  # Not a periodic job


def test_periodic_job_with_initial_delay(mq_fixture, rm_fixture):
    """Test periodic job with initial delay before first execution."""
    execution_count = [0]
    execution_times = []

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that records execution time."""
        execution_count[0] += 1
        execution_times.append(time.time())

    # Replace handler
    mq_fixture._do = process_job

    # Create a periodic job with 2-second initial delay, then 1-second intervals
    job = Job(
        payload=SimpleTask(name="delayed_test", value=999),
        status=TaskStatus.PENDING,
        periodic_initial_delay_seconds=2,  # Wait 2 seconds before first run
        periodic_interval_seconds=1,  # Then run every 1 second
        periodic_max_runs=3,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer and record start time
    start_time = time.time()
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for all runs to complete (2s initial + 1s + 1s + buffer)
    time.sleep(5.5)
    mq_fixture.stop_consuming()

    # Should execute 3 times
    assert execution_count[0] == 3, f"Expected 3 executions, got {execution_count[0]}"

    # Verify timing: first execution should be ~2s after start
    first_exec_delay = execution_times[0] - start_time
    assert 1.8 < first_exec_delay < 2.5, (
        f"Expected first execution after ~2s, got {first_exec_delay:.2f}s"
    )

    # Subsequent executions should be ~1s apart
    if len(execution_times) >= 2:
        second_delay = execution_times[1] - execution_times[0]
        assert 0.8 < second_delay < 1.5, (
            f"Expected ~1s between runs, got {second_delay:.2f}s"
        )


def test_periodic_job_callback_returns_false_to_stop(mq_fixture, rm_fixture):
    """Test that callback can return False to stop periodic execution."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that stops after 2 executions."""
        execution_count[0] += 1
        # Stop after 2 executions by returning False
        if execution_count[0] >= 2:
            return False
        return True  # Continue

    # Replace handler
    mq_fixture._do = process_job

    # Create a periodic job with max_runs=10, but callback will stop it at 2
    job = Job(
        payload=SimpleTask(name="callback_stop_test", value=123),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=10,  # Would normally run 10 times
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait enough time for 10 runs if it didn't stop (10 seconds + buffer)
    # But it should stop after 2 runs
    time.sleep(4)
    mq_fixture.stop_consuming()

    # Should execute exactly 2 times (stopped by callback)
    assert execution_count[0] == 2, (
        f"Expected 2 executions (stopped by callback), got {execution_count[0]}"
    )

    # Verify periodic_runs is 2
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.periodic_runs == 2


def test_periodic_job_callback_returns_none_continues(mq_fixture, rm_fixture):
    """Test that callback returning None (default) continues execution."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that returns None (implicit)."""
        execution_count[0] += 1
        # Implicitly returns None

    # Replace handler
    mq_fixture._do = process_job

    # Create a periodic job
    job = Job(
        payload=SimpleTask(name="implicit_none_test", value=456),
        status=TaskStatus.PENDING,
        periodic_interval_seconds=1,
        periodic_max_runs=3,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for all runs
    time.sleep(4)
    mq_fixture.stop_consuming()

    # Should execute 3 times (max_runs)
    assert execution_count[0] == 3, f"Expected 3 executions, got {execution_count[0]}"


# --- Implementation-specific tests (RabbitMQ only) ---
# --- Implementation-specific tests (RabbitMQ only) ---


@pytest.mark.skipif(not PIKA_AVAILABLE, reason="pika not installed")
class TestRabbitMQPeriodicJobsImplementation:
    """Tests for RabbitMQ-specific implementation details of periodic jobs."""

    def test_enqueue_periodic_job_creates_delay_queue(self, rm_fixture):
        """Test that _enqueue_periodic_job creates a delay queue with correct TTL."""

        def handler(resource):
            pass

        mq = RabbitMQMessageQueue(
            do=handler,
            resource_manager=rm_fixture,
            queue_prefix="test:",
        )

        # Mock the channel
        mock_channel = MagicMock()

        # Call _enqueue_periodic_job
        resource_id = "test-resource-123"
        interval_seconds = 5

        mq._enqueue_periodic_job(mock_channel, resource_id, interval_seconds)

        # Verify queue_declare was called with correct arguments
        expected_queue_name = f"{mq.queue_name}:periodic:{interval_seconds}s"
        mock_channel.queue_declare.assert_called_once_with(
            queue=expected_queue_name,
            durable=True,
            arguments={
                "x-message-ttl": interval_seconds * 1000,  # Convert to milliseconds
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": mq.queue_name,
            },
        )

        # Verify basic_publish was called
        mock_channel.basic_publish.assert_called_once()
        publish_call = mock_channel.basic_publish.call_args
        assert publish_call[1]["exchange"] == ""
        assert publish_call[1]["routing_key"] == expected_queue_name
        assert publish_call[1]["body"] == resource_id.encode("utf-8")
        # Check delivery_mode is Persistent (value is 2)
        assert (
            publish_call[1]["properties"].delivery_mode == 2
        )  # pika.DeliveryMode.Persistent

    def test_enqueue_periodic_job_different_intervals(self, rm_fixture):
        """Test that different intervals create different delay queues."""

        def handler(resource):
            pass

        mq = RabbitMQMessageQueue(
            do=handler,
            resource_manager=rm_fixture,
            queue_prefix="test:",
        )

        mock_channel = MagicMock()
        resource_id = "test-resource-456"

        # Enqueue with 5 second interval
        mq._enqueue_periodic_job(mock_channel, resource_id, 5)

        # Enqueue with 10 second interval
        mq._enqueue_periodic_job(mock_channel, resource_id, 10)

        # Should have declared two different queues
        assert mock_channel.queue_declare.call_count == 2

        # Check the queue names are different
        call_1_queue = mock_channel.queue_declare.call_args_list[0][1]["queue"]
        call_2_queue = mock_channel.queue_declare.call_args_list[1][1]["queue"]

        assert call_1_queue.endswith(":periodic:5s")
        assert call_2_queue.endswith(":periodic:10s")
        assert call_1_queue != call_2_queue

    def test_periodic_job_with_zero_interval(self, rm_fixture):
        """Test that jobs with 0 or None interval are not treated as periodic."""
        execution_count = [0]

        def handler(resource: Resource[Job[SimpleTask]]):
            execution_count[0] += 1

        mq = RabbitMQMessageQueue(
            do=handler,
            resource_manager=rm_fixture,
            queue_prefix="test:",
        )

        # Create a job with 0 interval (not periodic)
        job = Job(
            payload=SimpleTask(name="test_zero_interval", value=700),
            status=TaskStatus.PENDING,
            periodic_interval_seconds=0,
            periodic_max_runs=3,
        )

        with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
            job_info = rm_fixture.create(job)

        # Purge queue
        with mq._get_connection() as (_, channel):
            channel.queue_purge(mq.queue_name)

        # Start consumer
        mq.put(job_info.resource_id)
        consumer_thread = Thread(target=mq.start_consume, daemon=True)
        consumer_thread.start()

        # Wait
        time.sleep(2)
        mq.stop_consuming()

        # Should execute exactly once (not periodic)
        assert execution_count[0] == 1

        # Verify periodic_runs was not incremented (since it's not periodic)
        final_resource = rm_fixture.get(job_info.resource_id)
        assert final_resource.data.periodic_runs == 0
        assert final_resource.data.status == TaskStatus.COMPLETED
