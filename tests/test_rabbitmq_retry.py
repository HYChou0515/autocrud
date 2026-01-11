"""
Test RabbitMQ retry and dead letter queue functionality.
"""

import pytest
from uuid import uuid4
from datetime import datetime
from unittest.mock import MagicMock, patch, call
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueue
from autocrud.types import Job, TaskStatus, Resource, RevisionInfo, RevisionStatus


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


class MockChannel:
    """Mock RabbitMQ channel."""

    def __init__(self):
        self.queue_declare = MagicMock()
        self.basic_publish = MagicMock()
        self.basic_qos = MagicMock()
        self.basic_ack = MagicMock()
        self.basic_nack = MagicMock()
        self.start_consuming = MagicMock()
        self.stop_consuming = MagicMock()
        self.is_open = True
        self._callback = None
        self._consume_called = False

    def simulate_message(self, body: bytes, retry_count: int = 0):
        """Simulate receiving a message."""
        if self._callback is None:
            raise RuntimeError("No consumer callback registered")

        method = MagicMock()
        method.delivery_tag = "test-tag"

        properties = MagicMock()
        properties.headers = {"x-retry-count": retry_count} if retry_count > 0 else None

        self._callback(self, method, properties, body)

    def basic_consume(self, queue, on_message_callback):
        """Mock basic_consume and store callback."""
        self._callback = on_message_callback
        self._consume_called = True
        # Return a consumer tag
        return "consumer-tag-1"


class MockConnection:
    """Mock RabbitMQ connection."""

    def __init__(self, channel):
        self.channel_obj = channel
        self.is_closed = False

    def channel(self):
        return self.channel_obj

    def add_callback_threadsafe(self, callback):
        callback()


@pytest.fixture
def mock_resource_manager():
    """Create a mock resource manager."""
    rm = MagicMock()
    return rm


@pytest.fixture
def mock_rabbitmq_queue(mock_resource_manager):
    """Create a RabbitMQ queue with mocked connection."""
    mock_channel = MockChannel()
    mock_connection = MockConnection(mock_channel)

    with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
        mock_pika.URLParameters = MagicMock()
        mock_pika.BlockingConnection = MagicMock(return_value=mock_connection)

        # Mock BasicProperties to return a dict with the properties
        def mock_basic_properties(**kwargs):
            return kwargs

        mock_pika.BasicProperties = mock_basic_properties
        mock_pika.DeliveryMode.Persistent = 2

        queue = RabbitMQMessageQueue(
            resource_manager=mock_resource_manager,
            amqp_url="amqp://test",
            queue_name="test_queue",
            max_retries=3,
            retry_delay_seconds=10,
        )
        queue._channel = mock_channel
        queue._connection = mock_connection

        yield queue, mock_channel, mock_resource_manager


def test_init_declares_all_queues():
    """Test that initialization declares main, retry, and dead letter queues."""
    mock_channel = MockChannel()
    mock_connection = MockConnection(mock_channel)

    with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
        mock_pika.URLParameters = MagicMock()
        mock_pika.BlockingConnection = MagicMock(return_value=mock_connection)
        mock_pika.DeliveryMode.Persistent = 2

        rm = MagicMock()
        queue = RabbitMQMessageQueue(
            resource_manager=rm,
            queue_name="test_queue",
            max_retries=5,
            retry_delay_seconds=15,
        )

        # Check that all three queues were declared
        assert mock_channel.queue_declare.call_count == 3

        calls = mock_channel.queue_declare.call_args_list

        # Main queue
        assert calls[0] == call(queue="test_queue", durable=True)

        # Dead letter queue
        assert calls[1] == call(queue="test_queue_dead", durable=True)

        # Retry queue with TTL and DLX
        assert calls[2][1]["queue"] == "test_queue_retry"
        assert calls[2][1]["durable"] is True
        assert calls[2][1]["arguments"]["x-message-ttl"] == 15000  # 15 seconds in ms
        assert calls[2][1]["arguments"]["x-dead-letter-exchange"] == ""
        assert calls[2][1]["arguments"]["x-dead-letter-routing-key"] == "test_queue"


def test_callback_success_acks_message(mock_rabbitmq_queue):
    """Test that successful callback acks the message."""
    queue, mock_channel, mock_rm = mock_rabbitmq_queue

    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_rm.get.return_value = resource
    mock_rm.create_or_update.return_value = resource

    # Setup successful callback
    callback = MagicMock()

    # Start consuming (doesn't actually block in test)
    queue.start_consume(callback)

    # Simulate message
    mock_channel.simulate_message(b"test-id", retry_count=0)

    # Verify callback was called
    callback.assert_called_once()

    # Verify message was acked
    mock_channel.basic_ack.assert_called_once()


def test_callback_failure_sends_to_retry_queue(mock_rabbitmq_queue):
    """Test that failed callback sends message to retry queue."""
    queue, mock_channel, mock_rm = mock_rabbitmq_queue

    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_rm.get.return_value = resource

    # Setup failing callback
    callback = MagicMock(side_effect=Exception("Test error"))

    # Start consuming
    queue.start_consume(callback)

    # Simulate message (first attempt, retry_count=0)
    mock_channel.simulate_message(b"test-id", retry_count=0)

    # Verify callback was called
    callback.assert_called_once()

    # Verify message was published to retry queue
    publish_calls = [
        call
        for call in mock_channel.basic_publish.call_args_list
        if call[1]["routing_key"] == "test_queue_retry"
    ]
    assert len(publish_calls) == 1

    # Verify retry count was incremented
    props = publish_calls[0][1]["properties"]
    assert props["headers"]["x-retry-count"] == 1
    assert "Test error" in props["headers"]["x-last-error"]

    # Verify original message was acked
    mock_channel.basic_ack.assert_called_once()


def test_max_retries_sends_to_dead_queue(mock_rabbitmq_queue):
    """Test that exceeding max retries sends message to dead letter queue."""
    queue, mock_channel, mock_rm = mock_rabbitmq_queue

    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_rm.get.return_value = resource

    # Setup failing callback
    callback = MagicMock(side_effect=Exception("Test error"))

    # Start consuming
    queue.start_consume(callback)

    # Simulate message with retry_count = max_retries (3)
    mock_channel.simulate_message(b"test-id", retry_count=3)

    # Verify message was published to dead letter queue
    publish_calls = [
        call
        for call in mock_channel.basic_publish.call_args_list
        if call[1]["routing_key"] == "test_queue_dead"
    ]
    assert len(publish_calls) == 1

    # Verify retry count stayed the same (no more retries)
    props = publish_calls[0][1]["properties"]
    assert props["headers"]["x-retry-count"] == 3


def test_retry_count_progression(mock_rabbitmq_queue):
    """Test that retry count increments correctly through multiple failures."""
    queue, mock_channel, mock_rm = mock_rabbitmq_queue

    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_rm.get.return_value = resource

    # Setup failing callback
    callback = MagicMock(side_effect=Exception("Test error"))

    # Start consuming
    queue.start_consume(callback)

    # Test retry count progression: 0 -> 1 -> 2 -> 3 -> dead
    for retry_count in range(4):
        mock_channel.basic_publish.reset_mock()
        mock_channel.simulate_message(b"test-id", retry_count=retry_count)

        if retry_count < 3:
            # Should go to retry queue
            publish_calls = [
                call
                for call in mock_channel.basic_publish.call_args_list
                if call[1]["routing_key"] == "test_queue_retry"
            ]
            assert len(publish_calls) == 1
            props = publish_calls[0][1]["properties"]
            assert props["headers"]["x-retry-count"] == retry_count + 1
        else:
            # Should go to dead queue
            publish_calls = [
                call
                for call in mock_channel.basic_publish.call_args_list
                if call[1]["routing_key"] == "test_queue_dead"
            ]
            assert len(publish_calls) == 1


def test_critical_error_sends_to_retry(mock_rabbitmq_queue):
    """Test that critical errors (e.g., resource not found) also use retry mechanism."""
    queue, mock_channel, mock_rm = mock_rabbitmq_queue

    # Setup resource manager to throw error
    mock_rm.get.side_effect = Exception("Resource not found")

    # Setup callback (won't be called due to earlier error)
    callback = MagicMock()

    # Start consuming (this registers the callback)
    queue.start_consume(callback)

    # Simulate message
    mock_channel.simulate_message(b"test-id", retry_count=0)

    # Verify callback was NOT called
    callback.assert_not_called()

    # Verify message was published to retry queue
    publish_calls = [
        call
        for call in mock_channel.basic_publish.call_args_list
        if call[1]["routing_key"] == "test_queue_retry"
    ]
    assert len(publish_calls) == 1

    # Verify error message contains "Critical error"
    props = publish_calls[0][1]["properties"]
    assert "Critical error" in props["headers"]["x-last-error"]
    assert props["headers"]["x-retry-count"] == 1


def test_custom_retry_config():
    """Test that custom retry configuration is respected."""
    mock_channel = MockChannel()
    mock_connection = MockConnection(mock_channel)

    with patch("autocrud.message_queue.rabbitmq.pika") as mock_pika:
        mock_pika.URLParameters = MagicMock()
        mock_pika.BlockingConnection = MagicMock(return_value=mock_connection)
        mock_pika.DeliveryMode.Persistent = 2

        rm = MagicMock()
        queue = RabbitMQMessageQueue(
            resource_manager=rm,
            queue_name="custom_queue",
            max_retries=5,
            retry_delay_seconds=30,
        )

        assert queue.max_retries == 5
        assert queue.retry_delay_seconds == 30

        # Check retry queue was declared with correct TTL
        calls = mock_channel.queue_declare.call_args_list
        retry_queue_call = [c for c in calls if c[1]["queue"] == "custom_queue_retry"][
            0
        ]
        assert retry_queue_call[1]["arguments"]["x-message-ttl"] == 30000  # 30 seconds


def test_error_message_truncation(mock_rabbitmq_queue):
    """Test that very long error messages are truncated."""
    queue, mock_channel, mock_rm = mock_rabbitmq_queue

    # Setup mock resource
    resource = Resource(
        info=create_test_revision_info(),
        data=Job(payload="test-payload", status=TaskStatus.PENDING),
    )
    mock_rm.get.return_value = resource

    # Setup callback with very long error message
    long_error = "x" * 1000  # 1000 character error
    callback = MagicMock(side_effect=Exception(long_error))

    # Start consuming
    queue.start_consume(callback)

    # Simulate message
    mock_channel.simulate_message(b"test-id", retry_count=0)

    # Verify error message was truncated to 500 characters
    publish_calls = [
        call
        for call in mock_channel.basic_publish.call_args_list
        if call[1]["routing_key"] == "test_queue_retry"
    ]
    props = publish_calls[0][1]["properties"]
    assert len(props["headers"]["x-last-error"]) == 500
