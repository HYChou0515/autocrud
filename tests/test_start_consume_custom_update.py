"""Tests for start_consume with custom_update parameter.

Covers:
1. custom_update="all" starts all registered async update-job consumers
2. custom_update=["name"] starts specific update-job consumers
3. custom_update with invalid name raises ValueError
4. custom_creation + custom_update together starts both kinds
5. Both None falls back to own MQ consumer (original behaviour)
6. custom_update="all" with no registered jobs is a no-op
"""

import datetime as dt
import time

import pytest
from fastapi import Body, FastAPI
from fastapi.testclient import TestClient
from msgspec import Struct

from specstar.crud.core import SpecStar
from specstar.message_queue.simple import SimpleMessageQueueFactory
from specstar.types import TaskStatus

# ---------------------------------------------------------------------------
# Test Models
# ---------------------------------------------------------------------------


class Character(Struct):
    name: str
    level: int
    hp: int = 100


class TrainRequest(Struct):
    levels: int


class BoostPayload(Struct):
    amount: int


class GenerateRequest(Struct):
    base_name: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_crud(**kwargs) -> SpecStar:
    return SpecStar(
        default_user="tester",
        default_now=dt.datetime.now,
        message_queue_factory=SimpleMessageQueueFactory(max_retries=1),
        **kwargs,
    )


def _wait_for_job_completion(
    spec: SpecStar,
    job_resource_name: str,
    job_resource_id: str,
    timeout: float = 5.0,
):
    """Poll until the job reaches COMPLETED or FAILED status."""
    rm = spec.resource_managers[job_resource_name]
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        resource = rm.get(job_resource_id)
        if resource.data.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            return resource
        time.sleep(0.1)
    raise TimeoutError(f"Job {job_resource_id} did not complete within {timeout}s")


def _create_character(client, name="Alice", level=5, hp=100) -> str:
    """Create a Character via the HTTP API and return the resource_id."""
    resp = client.post(
        "/character/",
        json={"name": name, "level": level, "hp": hp},
    )
    assert resp.status_code == 200
    return resp.json()["resource_id"]


def _setup_two_update_actions(spec):
    """Register two async update actions on Character."""
    spec.add_model(Character, name="character")

    @spec.update_action("character", async_mode="job", label="Train", path="train")
    def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
        return Character(
            name=existing.name,
            level=existing.level + payload.levels,
            hp=existing.hp,
        )

    @spec.update_action("character", async_mode="job", label="Boost", path="boost")
    def boost(existing: Character, payload: BoostPayload = Body(...)) -> Character:
        return Character(
            name=existing.name,
            level=existing.level,
            hp=existing.hp + payload.amount,
        )

    return spec


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStartConsumeCustomUpdateAll:
    """custom_update='all' starts all async update-job consumers."""

    def test_custom_update_all_starts_consumers(self):
        spec = _make_crud()
        _setup_two_update_actions(spec)

        app = FastAPI()
        spec.apply(app)

        # Start all update-job consumers via custom_update="all"
        spec.get_resource_manager(Character).start_consume(
            block=False, custom_update="all"
        )

        client = TestClient(app)
        resource_id = _create_character(client, name="Alice", level=5, hp=100)

        # Submit train job
        resp = client.post(f"/character/{resource_id}/train", json={"levels": 3})
        assert resp.status_code == 202

        r = _wait_for_job_completion(spec, "train-job", resp.json()["job_resource_id"])
        assert r.data.status == TaskStatus.COMPLETED

        # Submit boost job
        resp2 = client.post(f"/character/{resource_id}/boost", json={"amount": 50})
        assert resp2.status_code == 202

        r2 = _wait_for_job_completion(
            spec, "boost-job", resp2.json()["job_resource_id"]
        )
        assert r2.data.status == TaskStatus.COMPLETED


class TestStartConsumeCustomUpdateSpecific:
    """custom_update=[...] starts only specific update-job consumers."""

    def test_custom_update_specific_names(self):
        spec = _make_crud()
        _setup_two_update_actions(spec)

        app = FastAPI()
        spec.apply(app)

        # Start only train-job consumer
        spec.get_resource_manager(Character).start_consume(
            block=False, custom_update=["train-job"]
        )

        client = TestClient(app)
        resource_id = _create_character(client, name="Bob", level=1, hp=50)

        # Train should work
        resp = client.post(f"/character/{resource_id}/train", json={"levels": 2})
        assert resp.status_code == 202

        r = _wait_for_job_completion(spec, "train-job", resp.json()["job_resource_id"])
        assert r.data.status == TaskStatus.COMPLETED

    def test_custom_update_invalid_name_raises(self):
        spec = _make_crud()
        _setup_two_update_actions(spec)

        app = FastAPI()
        spec.apply(app)

        rm = spec.get_resource_manager(Character)
        with pytest.raises(ValueError, match="not a registered async update-job"):
            rm.start_consume(block=False, custom_update=["nonexistent-job"])


class TestStartConsumeBothCreationAndUpdate:
    """custom_creation + custom_update together start both kinds."""

    def test_both_creation_and_update(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        @spec.create_action("character", async_mode="job", label="Generate")
        def generate(req: GenerateRequest = Body(...)) -> Character:
            return Character(name=req.base_name, level=1, hp=50)

        @spec.update_action("character", async_mode="job", label="Train", path="train")
        def train(existing: Character, payload: TrainRequest = Body(...)) -> Character:
            return Character(
                name=existing.name,
                level=existing.level + payload.levels,
                hp=existing.hp,
            )

        app = FastAPI()
        spec.apply(app)

        # Start both create and update consumers together
        spec.get_resource_manager(Character).start_consume(
            block=False, custom_creation="all", custom_update="all"
        )

        client = TestClient(app)

        # Test create job
        resp_create = client.post(
            "/character/generate", json={"base_name": "Generated"}
        )
        assert resp_create.status_code == 202

        r_create = _wait_for_job_completion(
            spec,
            "generate-job",
            resp_create.json()["job_resource_id"],
        )
        assert r_create.data.status == TaskStatus.COMPLETED

        # Test update job
        resource_id = _create_character(client, name="Charlie", level=3, hp=80)
        resp_update = client.post(f"/character/{resource_id}/train", json={"levels": 5})
        assert resp_update.status_code == 202

        r_update = _wait_for_job_completion(
            spec, "train-job", resp_update.json()["job_resource_id"]
        )
        assert r_update.data.status == TaskStatus.COMPLETED


class TestStartConsumeCustomUpdateNoJobs:
    """custom_update='all' with no registered update jobs is a no-op."""

    def test_custom_update_all_with_no_registered_jobs(self):
        spec = _make_crud()
        spec.add_model(Character, name="character")

        app = FastAPI()
        spec.apply(app)

        # Should not raise, just a no-op (no update jobs registered)
        spec.get_resource_manager(Character).start_consume(
            block=False, custom_update="all"
        )


class TestStartConsumeDefaultBehaviour:
    """Both None falls back to own MQ consumer (original behaviour preserved)."""

    def test_default_no_mq_raises(self):
        """Without message queue, start_consume() raises NotImplementedError."""
        spec = SpecStar(default_user="tester", default_now=dt.datetime.now)
        spec.add_model(Character, name="character")
        app = FastAPI()
        spec.apply(app)

        rm = spec.get_resource_manager(Character)
        with pytest.raises(
            NotImplementedError, match="Message queue is not configured"
        ):
            rm.start_consume()
