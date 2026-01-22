from unittest.mock import MagicMock

from msgspec import Struct

from autocrud.crud.core import AutoCRUD, LazyJobHandler
from autocrud.types import Job, Resource


class MyPayload(Struct):
    data: str


class MyJob(Job[MyPayload]):
    pass


def test_add_model_with_job_handler_factory():
    """Test that job_handler_factory is accepted and used lazily."""

    mock_handler = MagicMock()
    mock_factory = MagicMock(return_value=mock_handler)

    autocrud = AutoCRUD()

    # Add model with factory
    autocrud.add_model(
        MyJob,
        job_handler_factory=mock_factory,
        # We need a message queue factory active, simpler to rely on default or mock
        # Default AutoCRUD has SimpleMessageQueueFactory
    )

    # Factory should NOT be called yet
    mock_factory.assert_not_called()

    # Get resource manager to access MQ
    rm = autocrud.get_resource_manager(MyJob)
    mq = rm.message_queue

    # The 'do' callback in MQ should be our LazyJobHandler
    # Implementation detail check: SimpleMessageQueue stores callback in self._do
    assert isinstance(mq._do, LazyJobHandler)

    # Simulate a job execution
    res = Resource(
        info=MagicMock(),
        data=MyJob(payload=MyPayload(data="test")),
    )

    # Call the handler wrapper
    mq._do(res)

    # Now factory should be called once, and handler called once
    mock_factory.assert_called_once()
    mock_handler.assert_called_once_with(res)

    # Call again
    mq._do(res)

    # Factory not called again, handler called again
    mock_factory.assert_called_once()  # Still 1
    assert mock_handler.call_count == 2


def test_add_model_with_job_handler_priority():
    """Test that job_handler_factory takes priority over job_handler."""

    mock_handler_direct = MagicMock()

    mock_handler_from_factory = MagicMock()
    mock_factory = MagicMock(return_value=mock_handler_from_factory)

    autocrud = AutoCRUD()

    autocrud.add_model(
        MyJob,
        name="job-priority",
        job_handler=mock_handler_direct,
        job_handler_factory=mock_factory,
    )

    rm = autocrud.get_resource_manager("job-priority")
    mq = rm.message_queue

    assert isinstance(mq._do, LazyJobHandler)

    res = Resource(
        info=MagicMock(),
        data=MyJob(payload=MyPayload(data="test")),
    )

    mq._do(res)

    # Factory used
    mock_factory.assert_called_once()
    mock_handler_from_factory.assert_called_once()

    # Direct handler NOT used
    mock_handler_direct.assert_not_called()
