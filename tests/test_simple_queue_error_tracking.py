"""
Test SimpleMessageQueue error tracking functionality.
"""

import pytest
from unittest.mock import MagicMock
from autocrud.message_queue.simple import SimpleMessageQueue
from autocrud.types import Job, TaskStatus, Resource, RevisionInfo, RevisionStatus
from uuid import uuid4
from datetime import datetime


def create_test_revision_info(
    resource_id: str = "test-id", revision_id: str = "rev-1"
) -> RevisionInfo:
    """Helper function to create a test RevisionInfo."""
    return RevisionInfo(
        uid=uuid4(),
        resource_id=resource_id,
        revision_id=revision_id,
        status=RevisionStatus.draft,
        created_time=datetime.now(),
        updated_time=datetime.now(),
        created_by="test-user",
        updated_by="test-user",
    )


@pytest.fixture
def mock_resource_manager():
    """Create a mock resource manager."""
    return MagicMock()


@pytest.fixture
def simple_queue(mock_resource_manager):
    """Create a SimpleMessageQueue with mocked resource manager."""
    return SimpleMessageQueue(resource_manager=mock_resource_manager)


def test_error_message_recorded_on_failure(simple_queue, mock_resource_manager):
    """Test that error message is recorded in Job.result when task fails."""
    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_resource_manager.get.return_value = resource

    # Mock pop to return the job once, then None to stop the loop
    call_count = 0

    def mock_pop():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resource
        return None

    simple_queue.pop = mock_pop

    # Setup failing callback
    callback = MagicMock(side_effect=Exception("Processing failed"))

    # Start consuming (will process one job then stop)
    import threading

    consume_thread = threading.Thread(
        target=simple_queue.start_consume, args=(callback,)
    )
    consume_thread.start()

    # Wait a bit for processing
    import time

    time.sleep(0.2)

    # Stop consuming
    simple_queue.stop_consuming()
    consume_thread.join(timeout=1)

    # Verify Job was updated with error info
    update_calls = [
        call
        for call in mock_resource_manager.create_or_update.call_args_list
        if len(call[0]) > 1 and call[0][1].status == TaskStatus.FAILED
    ]

    assert len(update_calls) >= 1
    updated_job = update_calls[-1][0][1]
    assert updated_job.result == "Processing failed"
    assert updated_job.retries == 1


def test_retry_count_increments(simple_queue, mock_resource_manager):
    """Test that retry count increments on each failure."""
    # Setup mock resource with existing retry count
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(
            payload="test-payload",
            status=TaskStatus.PENDING,
            result="Previous error",
            retries=2,
        ),
    )
    mock_resource_manager.get.return_value = resource

    # Mock pop to return the job once, then None
    call_count = 0

    def mock_pop():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resource
        return None

    simple_queue.pop = mock_pop

    # Setup failing callback
    callback = MagicMock(side_effect=Exception("New error"))

    # Start consuming
    import threading

    consume_thread = threading.Thread(
        target=simple_queue.start_consume, args=(callback,)
    )
    consume_thread.start()

    # Wait a bit
    import time

    time.sleep(0.2)

    # Stop consuming
    simple_queue.stop_consuming()
    consume_thread.join(timeout=1)

    # Verify retry count incremented
    update_calls = [
        call
        for call in mock_resource_manager.create_or_update.call_args_list
        if len(call[0]) > 1 and call[0][1].status == TaskStatus.FAILED
    ]

    assert len(update_calls) >= 1
    updated_job = update_calls[-1][0][1]
    assert updated_job.result == "New error"  # New error overwrites old
    assert updated_job.retries == 3  # Incremented from 2 to 3


def test_error_overwrites_previous_error(simple_queue, mock_resource_manager):
    """Test that new error message overwrites previous one."""
    # Setup mock resource with old error
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(
            payload="test-payload",
            status=TaskStatus.PENDING,
            result="Old error message",
            retries=1,
        ),
    )
    mock_resource_manager.get.return_value = resource

    # Mock pop
    call_count = 0

    def mock_pop():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resource
        return None

    simple_queue.pop = mock_pop

    # Setup failing callback with new error
    callback = MagicMock(side_effect=Exception("Completely different error"))

    # Start consuming
    import threading

    consume_thread = threading.Thread(
        target=simple_queue.start_consume, args=(callback,)
    )
    consume_thread.start()

    # Wait a bit
    import time

    time.sleep(0.2)

    # Stop consuming
    simple_queue.stop_consuming()
    consume_thread.join(timeout=1)

    # Verify new error overwrites old
    update_calls = [
        call
        for call in mock_resource_manager.create_or_update.call_args_list
        if len(call[0]) > 1 and call[0][1].status == TaskStatus.FAILED
    ]

    assert len(update_calls) >= 1
    updated_job = update_calls[-1][0][1]
    assert updated_job.result == "Completely different error"
    assert "Old error message" not in updated_job.result


def test_successful_task_does_not_update_error(simple_queue, mock_resource_manager):
    """Test that successful tasks do not update error information."""
    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_resource_manager.get.return_value = resource

    # Mock pop
    call_count = 0

    def mock_pop():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return resource
        return None

    simple_queue.pop = mock_pop

    # Setup successful callback
    callback = MagicMock()

    # Start consuming
    import threading

    consume_thread = threading.Thread(
        target=simple_queue.start_consume, args=(callback,)
    )
    consume_thread.start()

    # Wait a bit
    import time

    time.sleep(0.2)

    # Stop consuming
    simple_queue.stop_consuming()
    consume_thread.join(timeout=1)

    # Verify no FAILED updates were made
    update_calls = [
        call
        for call in mock_resource_manager.create_or_update.call_args_list
        if len(call[0]) > 1 and call[0][1].status == TaskStatus.FAILED
    ]

    assert len(update_calls) == 0

    # Verify callback was called successfully
    callback.assert_called_once()
