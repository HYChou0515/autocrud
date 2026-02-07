"""
Tests for CeleryMessageQueue implementation.

重點測試：
- 基本功能
- 重試機制（含 kwargs/args bug）
- DelayRetry / NoRetry 異常
- 週期任務
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from msgspec import Struct

from autocrud.message_queue.basic import DelayRetry, NoRetry
from autocrud.message_queue.celery_queue import (
    CeleryMessageQueue,
    CeleryMessageQueueFactory,
)
from autocrud.resource_manager.core import ResourceManager, SimpleStorage
from autocrud.resource_manager.meta_store.simple import MemoryMetaStore
from autocrud.resource_manager.resource_store.simple import MemoryResourceStore
from autocrud.types import Job, Resource, TaskStatus


class TaskData(Struct):
    """Simple test task data."""

    message: str
    value: int = 0


@pytest.fixture
def celery_app():
    """Create a test Celery app (eager mode)."""
    try:
        from celery import Celery
    except ImportError:
        pytest.skip("celery not installed")

    app = Celery("test_app", broker="memory://", backend="cache+memory://")
    app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        result_backend="cache+memory://",
    )
    return app


@pytest.fixture
def celery_app_non_eager():
    """Create a test Celery app (non-eager for manual invocation)."""
    try:
        from celery import Celery
    except ImportError:
        pytest.skip("celery not installed")

    app = Celery("test_app", broker="memory://", backend="cache+memory://")
    app.conf.update(task_always_eager=False, result_backend="cache+memory://")
    return app


@pytest.fixture
def resource_manager():
    """Create a test ResourceManager."""
    import datetime as dt

    meta_store = MemoryMetaStore()
    resource_store = MemoryResourceStore()
    storage = SimpleStorage(meta_store=meta_store, resource_store=resource_store)
    return ResourceManager(
        Job[TaskData],
        storage=storage,
        default_user="system",
        default_now=lambda: dt.datetime.now(),
    )


def test_basic_job_execution(celery_app, resource_manager):
    """Test basic job creation, enqueue, and execution."""
    results = []

    def callback(resource: Resource[Job[TaskData]]):
        results.append(resource.data.payload.message)

    queue = CeleryMessageQueue(
        do=callback,
        resource_manager=resource_manager,
        celery_app=celery_app,
    )

    with resource_manager.meta_provide(user="test_user"):
        job = resource_manager.create(Job(payload=TaskData(message="Hello")))
        queue.put(job.resource_id)

    assert results == ["Hello"]
    assert resource_manager.get(job.resource_id).data.status == TaskStatus.COMPLETED


def test_retry_on_failure(celery_app, resource_manager):
    """Test job retry mechanism."""
    attempts = [0]

    def failing_callback(resource: Resource[Job[TaskData]]):
        attempts[0] += 1
        if attempts[0] < 3:
            raise ValueError("Fail")

    queue = CeleryMessageQueue(
        do=failing_callback,
        resource_manager=resource_manager,
        celery_app=celery_app,
        max_retries=5,
    )

    with resource_manager.meta_provide(user="test_user"):
        job = resource_manager.create(Job(payload=TaskData(message="Retry test")))

    with patch.object(queue._celery_task, "retry") as mock_retry:
        mock_retry.return_value = None
        try:
            queue.put(job.resource_id)
        except Exception:
            pass

    updated = resource_manager.get(job.resource_id)
    assert updated.data.status == TaskStatus.FAILED
    assert updated.data.retries == 1


def test_no_retry_exception(celery_app, resource_manager):
    """Test NoRetry exception prevents retries."""

    def no_retry_callback(resource: Resource[Job[TaskData]]):
        raise NoRetry("Stop")

    queue = CeleryMessageQueue(
        do=no_retry_callback,
        resource_manager=resource_manager,
        celery_app=celery_app,
        max_retries=5,
    )

    with resource_manager.meta_provide(user="test_user"):
        job = resource_manager.create(Job(payload=TaskData(message="No retry")))
        queue.put(job.resource_id)

    updated = resource_manager.get(job.resource_id)
    assert updated.data.status == TaskStatus.FAILED
    assert updated.data.retries == 1


def test_delay_retry_exception(celery_app, resource_manager):
    """Test DelayRetry exception schedules delayed retry."""
    attempts = [0]

    def delay_retry_callback(resource: Resource[Job[TaskData]]):
        attempts[0] += 1
        if attempts[0] == 1:
            raise DelayRetry(delay_seconds=10)

    queue = CeleryMessageQueue(
        do=delay_retry_callback,
        resource_manager=resource_manager,
        celery_app=celery_app,
    )

    with resource_manager.meta_provide(user="test_user"):
        job = resource_manager.create(Job(payload=TaskData(message="Delay")))

    with patch.object(queue, "_schedule_delayed_job") as mock_schedule:
        queue.put(job.resource_id)
        mock_schedule.assert_called_once_with(job.resource_id, 10)


def test_periodic_job(celery_app, resource_manager):
    """Test periodic job execution."""

    def callback(resource: Resource[Job[TaskData]]):
        pass

    queue = CeleryMessageQueue(
        do=callback,
        resource_manager=resource_manager,
        celery_app=celery_app,
    )

    with resource_manager.meta_provide(user="test_user"):
        job = resource_manager.create(
            Job(
                payload=TaskData(message="Periodic"),
                periodic_interval_seconds=60,
                periodic_max_runs=3,
            )
        )

    with patch.object(queue, "_schedule_delayed_job") as mock_schedule:
        queue.put(job.resource_id)
        assert mock_schedule.call_count == 1
        assert mock_schedule.call_args[0] == (job.resource_id, 60)


def test_factory(celery_app, resource_manager):
    """Test CeleryMessageQueueFactory."""

    factory = CeleryMessageQueueFactory(
        celery_app=celery_app,
        max_retries=5,
        retry_delay_seconds=20,
    )

    queue = factory.build(lambda r: None)(resource_manager)

    assert isinstance(queue, CeleryMessageQueue)
    assert queue.max_retries == 5
    assert queue.retry_delay_seconds == 20


def test_retry_parameter_passing_bug(celery_app_non_eager, resource_manager):
    """
    **核心 Bug 測試**

    驗證 retry() 使用 args 而非 kwargs，避免參數重複。

    Bug: retry(kwargs={"resource_id": X, "retry_count": 1})
         → Celery 調用 task(resource_id, resource_id=X, retry_count=1)
         → TypeError: got multiple values for argument 'resource_id'

    Fix: retry(args=(resource_id, retry_count + 1))
         → Celery 調用 task(resource_id, retry_count + 1)
         → 正常執行
    """
    from celery.exceptions import Retry as CeleryRetry

    def failing_callback(resource: Resource[Job[TaskData]]):
        raise ValueError("Fail")

    queue = CeleryMessageQueue(
        do=failing_callback,
        resource_manager=resource_manager,
        celery_app=celery_app_non_eager,
        max_retries=2,
    )

    with resource_manager.meta_provide(user="test_user"):
        job = resource_manager.create(Job(payload=TaskData(message="Test")))

    task = queue._celery_task

    # 捕獲 retry() 調用參數
    retry_args = []
    retry_kwargs = []

    def mock_retry(*args, **kwargs):
        retry_args.append(kwargs.get("args"))
        retry_kwargs.append(kwargs.get("kwargs"))
        raise CeleryRetry("Captured", exc=kwargs.get("exc"))

    with patch.object(task, "retry", side_effect=mock_retry):
        try:
            task(job.resource_id, retry_count=0)
        except CeleryRetry:
            pass

    assert len(retry_args) > 0, "retry() should be called"

    # 模擬 Celery worker 重新執行
    if retry_kwargs[0] is not None:
        # 使用 kwargs → 會產生 TypeError
        task(job.resource_id, **retry_kwargs[0])
        raise AssertionError("Should cause TypeError with kwargs")

    elif retry_args[0] is not None:
        # 使用 args → 正確
        try:
            task(*retry_args[0])
        except TypeError as e:
            if "got multiple values for argument" in str(e):
                raise AssertionError(f"Args should not cause conflict: {e}")
        except (CeleryRetry, Exception):
            pass  # 其他異常可接受

    else:
        raise AssertionError("retry() must use args or kwargs")
