import datetime as dt
import pytest
from msgspec import Struct
from autocrud.message_queue.rabbitmq import RabbitMQMessageQueue
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.message_queue.simple import SimpleMessageQueue
from autocrud.types import (
    IMessageQueue,
    Job,
    Resource,
    TaskStatus,
    IndexableField,
    ResourceMetaSearchQuery,
)


class Payload(Struct):
    task_name: str
    priority: int


def get_simple_queue(rm):
    return SimpleMessageQueue(rm)


def get_rabbitmq_queue(rm):
    queue_name = "test_autocrud_jobs_unified"
    mq = RabbitMQMessageQueue(rm, queue_name=queue_name)
    # Purge to ensure a clean state for each test
    mq._channel.queue_purge(queue_name)
    return mq


@pytest.fixture(params=["simple", "rabbitmq"])
def mq_context(request: pytest.FixtureRequest):
    """Fixture that provides both the queue implementation and its associated resource manager."""
    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store, resource_store)
    rm = ResourceManager(
        Job[Payload],
        storage=storage,
        indexed_fields=[IndexableField(field_path="status", field_type=str)],
    )

    if request.param == "simple":
        queue = get_simple_queue(rm)
    else:
        queue = get_rabbitmq_queue(rm)

    return queue, rm


class TestMessageQueueUnified:
    """
    Unified tests for all IMessageQueue implementations.
    Ensures that behavior remains consistent regardless of the underlying transport.
    """

    @pytest.fixture(autouse=True)
    def setup_method(
        self, mq_context: tuple[IMessageQueue[Payload], ResourceManager[Job[Payload]]]
    ):
        self.queue, self.rm = mq_context

    def test_workflow(self):
        queue, rm = self.queue, self.rm
        user = "test_user"
        now = dt.datetime(2023, 1, 1, 12, 0, 0, tzinfo=dt.timezone.utc)

        with rm.meta_provide(user=user, now=now):
            # 1. Enqueue
            payload1 = Payload(task_name="task1", priority=1)
            res1 = queue.put(payload1)
            assert res1.data.status == TaskStatus.PENDING
            assert res1.data.payload == payload1

            # 2. Enqueue second
            now2 = now + dt.timedelta(seconds=1)
            with rm.meta_provide(user=user, now=now2):
                payload2 = Payload(task_name="task2", priority=2)
                res2 = queue.put(payload2)

        # 3. Pop (FIFO) - should get task1
        now3 = now + dt.timedelta(seconds=2)
        with rm.meta_provide(user="consumer", now=now3):
            job1 = queue.pop()
            assert job1 is not None
            assert job1.info.resource_id == res1.info.resource_id
            assert job1.data.status == TaskStatus.PROCESSING

            # 4. Complete
            completed = queue.complete(job1.info.resource_id, result="done")
            assert completed.data.status == TaskStatus.COMPLETED
            assert completed.data.result == "done"

            # 5. Pop next
            job2 = queue.pop()
            assert job2 is not None
            assert job2.info.resource_id == res2.info.resource_id

            # 6. Fail
            failed = queue.fail(job2.info.resource_id, error="oops")
            assert failed.data.status == TaskStatus.FAILED
            assert failed.data.result == "oops"

            # 7. Empty
            assert queue.pop() is None

    def test_aliases(self):
        queue, rm = self.queue, self.rm
        user = "test_user"
        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user=user, now=now):
            queue.add_task(Payload(task_name="t1", priority=0))
            queue.enqueue(Payload(task_name="t2", priority=0))

            assert queue.dequeue() is not None
            assert queue.next_task() is not None

    def test_missing_resource_resilience(self):
        """Tests that the queue handles cases where the resource is deleted out-of-band."""
        queue, rm = self.queue, self.rm
        payload = Payload(task_name="ghost_task", priority=0)

        with rm.meta_provide(user="ghost", now=dt.datetime.now(dt.timezone.utc)):
            res_put = queue.put(payload)
            # Delete direct from RM
            rm.delete(res_put.info.resource_id)

            # Dequeue should skip/handle the missing resource and return None
            res_pop = queue.pop()
            assert res_pop is None

    def test_consume_loop(self):
        import time
        import threading

        queue_producer, rm = self.queue, self.rm

        # Prepare Data
        user = "producer"
        now = dt.datetime.now(dt.timezone.utc)
        with rm.meta_provide(user=user, now=now):
            # Job 1: Success
            queue_producer.put(Payload(task_name="success_job", priority=1))
            # Job 2: Fail logic
            queue_producer.put(Payload(task_name="fail_job", priority=2))

        results = []
        consumer_queue_ref: IMessageQueue[Payload] = None

        def worker_logic(resource: Resource[Job[Payload]]):
            name = resource.data.payload.task_name
            if name == "fail_job":
                raise ValueError("Intentional Fail")
            results.append(name)

        def run_queue():
            nonlocal consumer_queue_ref
            # Create a consumer instance for this thread
            if isinstance(queue_producer, RabbitMQMessageQueue):
                queue_consumer = RabbitMQMessageQueue(
                    rm, queue_name=queue_producer.queue_name
                )
            else:
                queue_consumer = queue_producer  # SimpleMQ is mostly thread safe for this or relies on RM safety

            consumer_queue_ref = queue_consumer

            # Setup context for the consumer thread
            with rm.meta_provide(user="consumer", now=dt.datetime.now(dt.timezone.utc)):
                try:
                    queue_consumer.start_consume(worker_logic)
                except Exception:
                    # Ignore errors during stop/shutdown
                    pass

        t = threading.Thread(target=run_queue)
        t.start()

        # Wait for consumer to initialize
        start_wait = time.time()
        while consumer_queue_ref is None and time.time() - start_wait < 5:
            time.sleep(0.1)

        # Wait for processing
        time.sleep(1.0)

        # Stop
        if consumer_queue_ref:
            consumer_queue_ref.stop_consuming()
        t.join(timeout=2)

        # Verify
        assert "success_job" in results
        assert "fail_job" not in results

        # Check RM status
        with rm.meta_provide(user="checker", now=dt.datetime.now(dt.timezone.utc)):
            all_jobs = rm.search_resources(ResourceMetaSearchQuery())
            statuses = {}
            for meta in all_jobs:
                res = rm.get(meta.resource_id)
                name = res.data.payload.task_name
                statuses[name] = res.data.status

            assert statuses.get("success_job") == TaskStatus.COMPLETED
            assert statuses.get("fail_job") == TaskStatus.FAILED
