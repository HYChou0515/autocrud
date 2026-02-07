"""Tests for DelayRetry exception mechanism."""

import datetime as dt
import time
from threading import Thread

import pytest
from msgspec import Struct

from autocrud.message_queue.basic import DelayRetry
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
    attempt: int = 0


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
        mq = RabbitMQMessageQueue(
            do=dummy_handler,
            resource_manager=rm_fixture,
            queue_prefix="test:",
            max_retries=3,
        )
        # Clear queue before test
        with mq._get_connection() as (_, channel):
            channel.queue_purge(mq.queue_name)

    yield mq

    # Cleanup
    if hasattr(mq, "stop_consuming"):
        mq.stop_consuming()


def test_delay_retry_basic(mq_fixture, rm_fixture):
    """Test DelayRetry delays execution by specified seconds."""
    execution_times = []
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that uses DelayRetry."""
        execution_count[0] += 1
        execution_times.append(time.time())

        # First attempt: delay 2 seconds
        if execution_count[0] == 1:
            raise DelayRetry(2)

        # Second attempt: success
        return

    # Replace handler
    mq_fixture._do = process_job

    # Create a job
    job = Job(
        payload=SimpleTask(name="delay_test", value=42),
        status=TaskStatus.PENDING,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for both executions
    time.sleep(3.5)
    mq_fixture.stop_consuming()

    # Should execute twice (original + delayed retry)
    assert execution_count[0] == 2, f"Expected 2 executions, got {execution_count[0]}"

    # Verify timing: second execution should be ~2s after first
    if len(execution_times) >= 2:
        delay = execution_times[1] - execution_times[0]
        assert 1.5 < delay < 3, f"Expected ~2s delay, got {delay:.2f}s"

    # Verify final status is COMPLETED
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED
    assert final_resource.data.retries == 0  # Retry count should be reset


def test_delay_retry_multiple_times(mq_fixture, rm_fixture):
    """Test DelayRetry can be raised multiple times."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        """Process function that delays 3 times."""
        execution_count[0] += 1

        # Delay 3 times, then succeed
        if execution_count[0] <= 3:
            raise DelayRetry(1)

    # Replace handler
    mq_fixture._do = process_job

    # Create a job
    job = Job(
        payload=SimpleTask(name="multi_delay", value=99),
        status=TaskStatus.PENDING,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for all executions
    time.sleep(5)
    mq_fixture.stop_consuming()

    # Should execute 4 times (3 delays + 1 success)
    assert execution_count[0] == 4, f"Expected 4 executions, got {execution_count[0]}"

    # Verify final status
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED


def test_delay_retry_different_intervals(mq_fixture, rm_fixture):
    """Test DelayRetry with different delay intervals."""
    execution_count = [0]
    delays = []

    def handler(resource: Resource[Job[SimpleTask]]):
        execution_count[0] += 1
        delays.append(time.time())

        # Use different delays each time
        if execution_count[0] == 1:
            raise DelayRetry(1)
        elif execution_count[0] == 2:
            raise DelayRetry(2)

    # Replace handler
    mq_fixture._do = handler

    # Create a job
    job = Job(
        payload=SimpleTask(name="variable_delay", value=456),
        status=TaskStatus.PENDING,
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for all executions
    time.sleep(5)
    mq_fixture.stop_consuming()

    # Should execute 3 times
    assert execution_count[0] == 3

    # Verify final status
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.status == TaskStatus.COMPLETED


def test_delay_retry_exception_message():
    """Test that DelayRetry exception has correct message."""
    exception = DelayRetry(60)
    assert exception.delay_seconds == 60
    assert "60 seconds" in str(exception)


def test_delay_retry_resets_retry_count(mq_fixture, rm_fixture):
    """Test that DelayRetry resets the retry count to 0."""
    execution_count = [0]

    def process_job(resource: Resource[Job[SimpleTask]]):
        execution_count[0] += 1
        if execution_count[0] == 1:
            raise DelayRetry(1)

    # Replace handler
    mq_fixture._do = process_job

    # Create a job with initial retries
    job = Job(
        payload=SimpleTask(name="retry_reset", value=789),
        status=TaskStatus.PENDING,
        retries=3,  # Start with some retries
    )

    with rm_fixture.meta_provide(user="test_user", now=dt.datetime.now()):
        job_info = rm_fixture.create(job)

    # Start consumer
    mq_fixture.put(job_info.resource_id)
    consumer_thread = Thread(target=mq_fixture.start_consume, daemon=True)
    consumer_thread.start()

    # Wait for executions
    time.sleep(3)
    mq_fixture.stop_consuming()

    # Verify retry count was reset to 0
    final_resource = rm_fixture.get(job_info.resource_id)
    assert final_resource.data.retries == 0
    assert final_resource.data.status == TaskStatus.COMPLETED
