"""Test AutoCRUD message queue integration."""

from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import Job


class EmailPayload(Struct):
    """Email job payload."""

    to: str
    subject: str
    body: str


class EmailJob(Job[EmailPayload]):
    """Email job - subclass of Job."""

    pass


class NotAJob(Struct):
    """Regular struct, not a Job."""

    name: str
    value: int


def test_autocrud_auto_creates_mq_for_job_subclass():
    """Test that AutoCRUD automatically creates message queue for Job subclasses."""
    crud = AutoCRUD(storage_factory=MemoryStorageFactory())

    # Add a Job subclass - should automatically get a message queue
    crud.add_model(EmailJob, name="email-jobs")

    # Verify message queue was created
    assert "email-jobs" in crud.message_queues

    # Get the message queue
    mq = crud.get_message_queue("email-jobs")
    assert mq is not None

    # Can also get by model class
    mq2 = crud.get_message_queue(EmailJob)
    assert mq2 is mq


def test_autocrud_no_mq_for_non_job():
    """Test that regular models don't get message queues."""
    crud = AutoCRUD(storage_factory=MemoryStorageFactory())

    # Add a regular model - should NOT get a message queue
    crud.add_model(NotAJob, name="regular-model")

    # Verify no message queue was created
    assert "regular-model" not in crud.message_queues


def test_autocrud_mq_functionality():
    """Test that the auto-created message queue works correctly."""
    import datetime as dt

    crud = AutoCRUD(storage_factory=MemoryStorageFactory())
    # Need to set indexed_fields for status to enable searching
    crud.add_model(EmailJob, name="email-jobs", indexed_fields=[("status", str)])

    # Get resource manager to set context
    rm = crud.get_resource_manager("email-jobs")
    mq = crud.get_message_queue("email-jobs")

    # Enqueue a job
    with rm.meta_provide(user="test-user", now=dt.datetime.now()):
        payload = EmailPayload(
            to="user@example.com", subject="Test Email", body="This is a test"
        )
        job_resource = mq.put(payload)

    # Verify job was created
    assert job_resource.data.payload.to == "user@example.com"
    assert job_resource.data.payload.subject == "Test Email"

    # Pop the job
    with rm.meta_provide(user="worker", now=dt.datetime.now()):
        next_job = mq.pop()

    assert next_job is not None
    assert next_job.data.payload.to == "user@example.com"

    # Complete the job
    with rm.meta_provide(user="worker", now=dt.datetime.now()):
        completed = mq.complete(next_job.info.resource_id, result="Email sent")

    assert completed.data.result == "Email sent"


def test_autocrud_custom_mq_factory():
    """Test using a custom message queue factory."""
    custom_factory = SimpleMessageQueueFactory()
    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(), message_queue_factory=custom_factory
    )

    crud.add_model(EmailJob, name="email-jobs")

    # Should use the custom factory
    assert "email-jobs" in crud.message_queues
    mq = crud.get_message_queue("email-jobs")
    assert mq is not None


def test_autocrud_override_mq_factory_per_model():
    """Test overriding message queue factory on a per-model basis."""
    # Default factory
    default_factory = SimpleMessageQueueFactory()
    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(), message_queue_factory=default_factory
    )

    # Model 1: use default factory
    crud.add_model(EmailJob, name="email-jobs-default")

    # Model 2: use custom factory
    custom_factory = SimpleMessageQueueFactory()

    class SmsPayload(Struct):
        phone: str
        message: str

    class SmsJob(Job[SmsPayload]):
        pass

    crud.add_model(SmsJob, name="sms-jobs", message_queue_factory=custom_factory)

    # Both should have message queues
    assert "email-jobs-default" in crud.message_queues
    assert "sms-jobs" in crud.message_queues


def test_autocrud_disable_mq_for_specific_job():
    """Test explicitly disabling message queue for a specific Job model."""
    crud = AutoCRUD(storage_factory=MemoryStorageFactory())

    # Disable message queue by passing None
    crud.add_model(EmailJob, name="email-jobs-no-mq", message_queue_factory=None)

    # Should NOT have a message queue
    assert "email-jobs-no-mq" not in crud.message_queues


def test_autocrud_generic_job():
    """Test with the generic Job[T] type directly."""
    import datetime as dt

    crud = AutoCRUD(storage_factory=MemoryStorageFactory())

    # Add Job[EmailPayload] directly
    crud.add_model(Job[EmailPayload], name="generic-email-jobs")

    # Should get a message queue
    assert "generic-email-jobs" in crud.message_queues

    mq = crud.get_message_queue("generic-email-jobs")
    rm = crud.get_resource_manager("generic-email-jobs")

    # Test it works
    with rm.meta_provide(user="test", now=dt.datetime.now()):
        payload = EmailPayload(
            to="test@example.com", subject="Generic Job Test", body="Testing"
        )
        job = mq.put(payload)

    assert job.data.payload.to == "test@example.com"
