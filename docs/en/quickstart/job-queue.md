# Quickstart - Job Queue

AutoCRUD can treat jobs as first-class resources.

That means background work is not just pushed into a broker and forgotten. Each job can carry structured input, status, history, and management metadata.

Queue setup is part of the broader backend story. This page focuses on the job-specific workflow, while the [backend setup guide](/autocrud/guides/backend-setup) helps when you are ready to choose the right persistence and queue shape for your environment.

This quickstart shows the smallest useful setup:

- choose a queue backend
- define a job payload
- register a job handler
- start a consumer
- submit a job
- poll for completion

---

## 0. Choose a queue backend

For first-time setup, make the queue backend explicit.
That removes ambiguity about where jobs are processed.

```python
from autocrud import crud
from autocrud.message_queue import SimpleMessageQueueFactory

crud.configure(
    message_queue_factory=SimpleMessageQueueFactory(),
)
```

Use this for local development and same-process consumers.
For production worker deployments, prefer `RabbitMQMessageQueueFactory()`.
Use `CeleryMessageQueueFactory()` mainly when your platform already standardizes on Celery.

---

## Why use the built-in job model

Traditional queue systems are powerful, but they often leave application teams to build extra layers for:

- job status tracking
- retry and rerun workflows
- audit history
- operator visibility
- UI-based inspection and manual operations

AutoCRUD wraps queue execution in a resource-oriented model so that jobs are easier to operate and reason about.

---

## 1. Define a payload and job type

In this example, users submit a model-training task with a dataset ID, algorithm, and training parameters.

```python
from typing import Any, Literal

import msgspec

from autocrud.types import Job, Resource


class TrainingPayload(msgspec.Struct):
    data_id: str
    algo: Literal["random-forest", "mlp"]
    params: dict[str, Any]


class TrainingJob(Job[TrainingPayload]):
    pass


def training(job: Resource[TrainingJob]) -> TrainingJob:
    print(f"start training job created by {job.info.created_by}")

    data = get_data(job.data.payload.data_id)
    model = train(
        job.data.payload.algo,
        data,
        job.data.payload.params,
    )

    print(f"trained model id: {model.id}")
    return job.data
```

Here:

- `TrainingPayload` defines the input shape
- `TrainingJob` is the resource type stored and tracked by AutoCRUD
- `training()` is the handler that performs the work

---

## 2. Register the job handler

Once the schema and handler are ready, register them with AutoCRUD:

```python
from autocrud import Schema, crud
from autocrud.message_queue import SimpleMessageQueueFactory

crud.configure(
    message_queue_factory=SimpleMessageQueueFactory(),
)

crud.add_model(
    Schema(TrainingJob, "v1"),
    job_handler=training,
)
```

After this, AutoCRUD knows which resource type represents the job and which function should process it.

---

## 3. Start the consumer

Get the resource manager for the job model and start consuming messages:

```python
mgr = crud.get_resource_manager(TrainingJob)
mgr.start_consume(
    # block=False
)
```

If you submit jobs and run the consumer in the same process, use `block=False` so the consumer does not prevent the rest of your script from continuing.

---

## 4. Submit a job

You can now create a new job through the Python API:

```python
job_info = mgr.create(
    TrainingJob(
        payload=TrainingPayload(
            data_id="data:1",
            algo="random-forest",
            params={"n": 100},
        )
    )
)
```

Once created, the job enters the queue and is picked up by the consumer.

You can also trigger jobs through the HTTP API or the generated Web UI when those are enabled.

See also:

- [Backend setup guide](/autocrud/guides/backend-setup)
- [Routes generation (FastAPI)](/autocrud/howto/routes)
- [Web UI](/autocrud/howto/web-ui)

---

## 5. Check the job status

A simple polling loop is often enough to verify the workflow during development:

```python
import time
from autocrud import TaskStatus

job_id = job_info.resource_id

for _ in range(10):
    job = mgr.get(job_id)

    if job.data.status == TaskStatus.COMPLETED:
        print("job completed")
        break

    if job.data.status == TaskStatus.FAILED:
        raise RuntimeError(job.data.errmsg or "job failed")

    time.sleep(0.5)
else:
    raise TimeoutError("job did not complete in time")
```

Typical states include:

- `pending`
- `processing`
- `completed`
- `failed`

If a job stays in `pending`, check that the consumer is running and that the selected queue backend is reachable.

---

## Full example

```python
import time
from typing import Any, Literal

import msgspec

from autocrud import Job, Schema, TaskStatus, crud
from autocrud.message_queue import SimpleMessageQueueFactory
from autocrud.types import Resource


class TrainingPayload(msgspec.Struct):
    data_id: str
    algo: Literal["random-forest", "mlp"]
    params: dict[str, Any]


class TrainingJob(Job[TrainingPayload]):
    pass


def get_data(data_id: str) -> dict[str, Any]:
    return {
        "data_id": data_id,
        "rows": 100,
    }


class _Model:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


def train(algo: str, data: dict[str, Any], params: dict[str, Any]) -> _Model:
    time.sleep(0.2)
    return _Model(model_id=f"{algo}-model-1")


def training(job: Resource[TrainingJob]) -> TrainingJob:
    print(f"start training job created by {job.info.created_by}")

    data = get_data(job.data.payload.data_id)
    model = train(
        job.data.payload.algo,
        data,
        job.data.payload.params,
    )

    print(f"trained model id: {model.id}")
    return job.data


def main() -> None:
    crud.configure(
        message_queue_factory=SimpleMessageQueueFactory(),
    )

    crud.add_model(
        Schema(TrainingJob, "v1"),
        job_handler=training,
    )

    mgr = crud.get_resource_manager(TrainingJob)
    mgr.start_consume(block=False)

    job_info = mgr.create(
        TrainingJob(
            payload=TrainingPayload(
                data_id="data:1",
                algo="random-forest",
                params={"n": 100},
            )
        )
    )

    print("job submitted:", job_info.resource_id)

    for _ in range(10):
        job = mgr.get(job_info.resource_id)
        print("current status:", job.data.status)

        if job.data.status == TaskStatus.COMPLETED:
            print("job completed")
            break

        if job.data.status == TaskStatus.FAILED:
            raise RuntimeError(job.data.errmsg or "job failed")

        time.sleep(0.5)
    else:
        raise TimeoutError("job did not complete in time")


if __name__ == "__main__":
    main()
```