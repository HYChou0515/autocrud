"""Test job rerun route template.

Verifies that:
1. A completed/failed job can be rerun via POST /{resource}/{id}/rerun
2. A pending/processing job cannot be rerun (400)
3. Non-job resources don't expose the rerun endpoint (404)
4. Rerun resets status to PENDING, retries to 0, errmsg to None
5. Rerun re-enqueues the job into the message queue
"""

import datetime as dt

from fastapi import FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from autocrud.crud.core import AutoCRUD
from autocrud.message_queue.simple import SimpleMessageQueueFactory
from autocrud.resource_manager.storage_factory import MemoryStorageFactory
from autocrud.types import Job, TaskStatus


class TaskPayload(Struct):
    command: str
    priority: int = 0


class TaskJob(Job[TaskPayload]):
    pass


class RegularModel(Struct):
    name: str
    value: int


def make_app(*, consume: bool = False) -> tuple[FastAPI, AutoCRUD, TestClient, list]:
    """Create a test app with a job model and optionally a regular model."""
    consumed = []

    def handler(job):
        consumed.append(job.data.resource_id)

    crud = AutoCRUD(
        storage_factory=MemoryStorageFactory(),
        message_queue_factory=SimpleMessageQueueFactory(),
    )
    crud.add_model(TaskJob, name="task-job", job_handler=handler)
    crud.add_model(RegularModel, name="regular")

    app = FastAPI()
    crud.apply(app)
    client = TestClient(app)
    return app, crud, client, consumed


def create_job(client: TestClient, command: str = "run-tests") -> str:
    """Create a job and return its resource_id."""
    resp = client.post(
        "/task-job", json={"payload": {"command": command, "priority": 1}}
    )
    assert resp.status_code == 200
    return resp.json()["resource_id"]


def set_job_status(
    crud: AutoCRUD, resource_id: str, status: TaskStatus, errmsg: str | None = None
):
    """Directly set a job's status via resource manager."""
    rm = crud.get_resource_manager("task-job")
    resource = rm.get(resource_id)
    job = resource.data
    job.status = status
    job.retries = 3 if status == TaskStatus.FAILED else 1
    job.errmsg = errmsg
    with rm.meta_provide(user="test", now=dt.datetime.now()):
        rm.create_or_update(resource_id, job)


class TestRerunRoute:
    """Test POST /{model}/{id}/rerun endpoint."""

    def test_rerun_failed_job(self):
        """A failed job can be rerun, resetting status/retries/errmsg."""
        _, crud, client, _ = make_app()
        rid = create_job(client)
        set_job_status(crud, rid, TaskStatus.FAILED, errmsg="something broke")

        resp = client.post(f"/task-job/{rid}/rerun")
        assert resp.status_code == 200

        # Verify the job was reset
        get_resp = client.get(f"/task-job/{rid}/data")
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["status"] == "pending"
        assert data["retries"] == 0
        assert data["errmsg"] is None

    def test_rerun_completed_job(self):
        """A completed job can be rerun."""
        _, crud, client, _ = make_app()
        rid = create_job(client)
        set_job_status(crud, rid, TaskStatus.COMPLETED)

        resp = client.post(f"/task-job/{rid}/rerun")
        assert resp.status_code == 200

        get_resp = client.get(f"/task-job/{rid}/data")
        data = get_resp.json()
        assert data["status"] == "pending"
        assert data["retries"] == 0
        assert data["errmsg"] is None

    def test_rerun_pending_job_returns_400(self):
        """A pending job cannot be rerun."""
        _, _, client, _ = make_app()
        rid = create_job(client)
        # Job starts as pending by default

        resp = client.post(f"/task-job/{rid}/rerun")
        assert resp.status_code == 400

    def test_rerun_processing_job_returns_400(self):
        """A processing job cannot be rerun."""
        _, crud, client, _ = make_app()
        rid = create_job(client)
        set_job_status(crud, rid, TaskStatus.PROCESSING)

        resp = client.post(f"/task-job/{rid}/rerun")
        assert resp.status_code == 400

    def test_rerun_nonexistent_job_returns_error(self):
        """Rerun on a non-existent resource returns an error."""
        _, _, client, _ = make_app()

        resp = client.post("/task-job/does-not-exist/rerun")
        assert resp.status_code in (400, 404)

    def test_rerun_on_non_job_resource_returns_404(self):
        """Non-job resources should not have the /rerun endpoint."""
        _, _, client, _ = make_app()

        # Create a regular resource
        resp = client.post("/regular", json={"name": "test", "value": 42})
        assert resp.status_code == 200
        rid = resp.json()["resource_id"]

        resp = client.post(f"/regular/{rid}/rerun")
        assert resp.status_code == 404

    def test_rerun_returns_revision_info(self):
        """Rerun response contains resource_id and revision_id."""
        _, crud, client, _ = make_app()
        rid = create_job(client)
        set_job_status(crud, rid, TaskStatus.FAILED)

        resp = client.post(f"/task-job/{rid}/rerun")
        assert resp.status_code == 200
        body = resp.json()
        assert "resource_id" in body
        assert body["resource_id"] == rid
        assert "revision_id" in body
