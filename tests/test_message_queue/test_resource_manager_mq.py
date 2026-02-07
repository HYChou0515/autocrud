"""Test ResourceManager message queue integration."""

import datetime as dt

import pytest
from msgspec import Struct

from autocrud import AutoCRUD
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import Job

# Check if celery is available
try:
    from celery import Celery

    from autocrud.message_queue.celery_queue import CeleryMessageQueueFactory

    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False


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


@pytest.mark.parametrize(
    "mq_factory_type",
    [
        pytest.param("simple", id="simple"),
    ],
)
def test_resource_manager_has_message_queue(mq_factory_type):
    """Test that ResourceManager exposes message queue via put_job/start_consume."""
    if mq_factory_type == "simple":
        mq_factory = SimpleMessageQueueFactory()
    else:  # celery
        app = Celery("test_app", broker="memory://", backend="cache+memory://")
        app.conf.update(task_always_eager=True, task_eager_propagates=True)
        mq_factory = CeleryMessageQueueFactory(celery_app=app)

    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(), message_queue_factory=mq_factory
    )

    def handler(job):
        pass

    # Add a Job subclass - should have a message queue
    crud.add_model(EmailJob, name="email-jobs", job_handler=handler)

    # Get the resource manager
    rm = crud.get_resource_manager("email-jobs")

    # Verify it has message queue methods that work
    with rm.meta_provide(user="test", now=dt.datetime.now()):
        payload = EmailPayload(to="test@example.com", subject="Test", body="Test")
        info = rm.create(EmailJob(payload=payload))
        job = rm.get(info.resource_id)
        assert job is not None

    # Add a regular model - should raise NotImplementedError
    crud.add_model(NotAJob, name="regular-model")
    rm_regular = crud.get_resource_manager("regular-model")

    # For regular (non-Job) models, there's no message queue
    assert rm_regular.message_queue is None


@pytest.mark.parametrize(
    "mq_factory_type",
    [
        pytest.param("simple", id="simple"),
    ],
)
def test_resource_manager_start_consume(mq_factory_type):
    """Test that ResourceManager start_consume works correctly."""
    # Track consumed jobs
    consumed_jobs = []

    def process_job(job):
        consumed_jobs.append(job)

    if mq_factory_type == "simple":
        mq_factory = SimpleMessageQueueFactory()
    else:  # celery
        app = Celery("test_app", broker="memory://", backend="cache+memory://")
        app.conf.update(task_always_eager=True, task_eager_propagates=True)
        mq_factory = CeleryMessageQueueFactory(celery_app=app)

    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(),
        message_queue_factory=mq_factory,
        default_now=dt.datetime.now,
        default_user="test-user",
    )
    crud.add_model(
        EmailJob,
        name="email-jobs",
        indexed_fields=[("status", str)],
        job_handler=process_job,
    )

    # Get the resource manager
    rm = crud.get_resource_manager("email-jobs")

    # Create a job
    with rm.meta_provide(user="test-user", now=dt.datetime.now()):
        payload = EmailPayload(
            to="user@example.com", subject="Test Email", body="This is a test"
        )
        info = rm.create(EmailJob(payload=payload))
        job_resource = rm.get(info.resource_id)

    # Verify job was created
    assert job_resource.data.payload.to == "user@example.com"

    # Override stop consuming behavior
    original_process = process_job

    def process_and_stop(job):
        original_process(job)
        rm.message_queue.stop_consuming()

    rm.message_queue._do = process_and_stop

    # Start consuming
    with rm.meta_provide(user="worker", now=dt.datetime.now()):
        rm.start_consume()

    assert len(consumed_jobs) == 1
    assert consumed_jobs[0].data.payload.to == "user@example.com"


def test_resource_manager_message_queue_none_for_non_job():
    """Test that ResourceManager has no message queue for non-Job types."""
    crud = AutoCRUD(storage_factory=MemoryStorageFactory())
    crud.add_model(NotAJob, name="regular-model")

    rm = crud.get_resource_manager("regular-model")

    # Should have no message queue
    assert rm.message_queue is None


def test_resource_manager_disabled_message_queue():
    """Test ResourceManager when message queue is explicitly disabled."""
    crud = AutoCRUD(storage_factory=MemoryStorageFactory())

    # Explicitly disable message queue
    crud.add_model(EmailJob, name="email-jobs", message_queue_factory=None)

    rm = crud.get_resource_manager("email-jobs")

    # Should have no message queue
    assert rm.message_queue is None


@pytest.mark.parametrize(
    "mq_factory_type",
    [
        pytest.param("simple", id="simple"),
    ],
)
def test_resource_manager_message_queue_workflow(mq_factory_type):
    """Test complete workflow using ResourceManager's put_job/start_consume."""
    # Track consumed jobs
    consumed_jobs = []

    def process_job(job):
        consumed_jobs.append(job)

    if mq_factory_type == "simple":
        mq_factory = SimpleMessageQueueFactory()
    else:  # celery
        app = Celery("test_app", broker="memory://", backend="cache+memory://")
        app.conf.update(task_always_eager=True, task_eager_propagates=True)
        mq_factory = CeleryMessageQueueFactory(celery_app=app)

    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(),
        message_queue_factory=mq_factory,
        default_now=dt.datetime.now,
        default_user="test-user",
    )
    crud.add_model(
        EmailJob,
        name="email-jobs",
        indexed_fields=[("status", str)],
        job_handler=process_job,
    )

    rm = crud.get_resource_manager("email-jobs")

    # Enqueue multiple jobs
    with rm.meta_provide(user="producer", now=dt.datetime.now()):
        info1 = rm.create(
            EmailJob(
                payload=EmailPayload(
                    to="user1@example.com", subject="Job 1", body="Body 1"
                )
            )
        )
        job1 = rm.get(info1.resource_id)
        info2 = rm.create(
            EmailJob(
                payload=EmailPayload(
                    to="user2@example.com", subject="Job 2", body="Body 2"
                )
            )
        )
        job2 = rm.get(info2.resource_id)

    # Override to stop after processing 2 jobs
    original_process = process_job

    def process_and_stop(job):
        original_process(job)
        if len(consumed_jobs) >= 2:
            rm.message_queue.stop_consuming()

    rm.message_queue._do = process_and_stop

    # Process jobs
    with rm.meta_provide(user="worker", now=dt.datetime.now()):
        rm.start_consume()

    assert len(consumed_jobs) == 2
    assert consumed_jobs[0].data.payload.to == "user1@example.com"
    assert consumed_jobs[1].data.payload.to == "user2@example.com"


@pytest.mark.parametrize(
    "mq_factory_type",
    [
        pytest.param("simple", id="simple"),
    ],
)
def test_resource_manager_custom_mq_factory(mq_factory_type):
    """Test ResourceManager with custom message queue factory."""
    if mq_factory_type == "simple":
        custom_factory = SimpleMessageQueueFactory()
    else:  # celery
        app = Celery("test_app", broker="memory://", backend="cache+memory://")
        app.conf.update(task_always_eager=True, task_eager_propagates=True)
        custom_factory = CeleryMessageQueueFactory(celery_app=app)

    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(), message_queue_factory=custom_factory
    )

    def handler(job):
        pass

    crud.add_model(EmailJob, name="email-jobs", job_handler=handler)

    rm = crud.get_resource_manager("email-jobs")

    # Should work with custom factory
    with rm.meta_provide(user="test", now=dt.datetime.now()):
        payload = EmailPayload(to="test@example.com", subject="Test", body="Test")
        info = rm.create(EmailJob(payload=payload))
        job = rm.get(info.resource_id)
        assert job is not None
