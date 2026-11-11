"""Pipeline authorization, concurrency and cancellation tests."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import src.api as api
import src.auth as auth
import src.feedback as feedback
import src.history as history
import src.sessions as sessions

PASSWORD = "temporary-pipeline-test-password"
BASE = "/v1/pipeline-runs"


@pytest.fixture
def jobs_client(tmp_path, monkeypatch):
    path = tmp_path / "jobs.db"
    for module in (api, auth, feedback, history, sessions):
        monkeypatch.setattr(module, "DATABASE", path)

    with TestClient(api.app) as client:
        for role in ("viewer", "operator", "maintainer"):
            auth.create_user(role, PASSWORD, role)
        yield client


def headers(client, role="maintainer"):
    response = client.post(
        "/v1/session",
        json={"username": role, "password": PASSWORD},
    )
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_anonymous_job_access_rejected(jobs_client):
    assert jobs_client.get(BASE).status_code == 401
    assert jobs_client.post(
        BASE, json={"reason": "Unauthorized attempt"}
    ).status_code == 401


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_non_maintainer_job_access_forbidden(jobs_client, role):
    token = headers(jobs_client, role)
    unknown = str(uuid4())

    assert jobs_client.get(BASE, headers=token).status_code == 403
    assert jobs_client.get(
        f"{BASE}/{unknown}", headers=token
    ).status_code == 403
    assert jobs_client.post(
        BASE, json={"reason": "Forbidden attempt"}, headers=token
    ).status_code == 403
    assert jobs_client.post(
        f"{BASE}/{unknown}/cancel",
        json={"reason": "Forbidden attempt"},
        headers=token,
    ).status_code == 403


def test_concurrent_requests_allow_only_one_job(jobs_client):
    token = headers(jobs_client)

    def create(number):
        return jobs_client.post(
            BASE, json={"reason": f"Concurrent request {number}"},
            headers=token,
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(create, (1, 2)))

    assert sorted(statuses) == [202, 409]
    items = jobs_client.get(BASE, headers=token).json()["items"]
    assert len(items) == 1
    assert items[0]["status"] == "queued"
    assert items[0]["deployment_enabled"] is False


def test_queued_cancel_and_retry_preserve_history(jobs_client):
    token = headers(jobs_client)
    response = jobs_client.post(
        BASE,
        json={"reason": "Initial job", "force_rebuild": True},
        headers=token,
    )
    assert response.status_code == 202
    original = response.json()
    assert original["force_rebuild"] is True
    assert [stage["id"] for stage in original["stages"]] == [
        "spark_etl", "train", "evaluate"
    ]

    endpoint = f"{BASE}/{original['job_id']}/cancel"
    cancelled = jobs_client.post(
        endpoint, json={"reason": "Cancel before execution"}, headers=token
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["finished_at"] is not None
    assert all(
        stage["status"] == "skipped" for stage in cancelled.json()["stages"]
    )
    assert jobs_client.post(
        endpoint, json={"reason": "Second cancellation"}, headers=token
    ).status_code == 409

    retry = jobs_client.post(
        BASE,
        json={"reason": "Explicit retry", "retry_of": original["job_id"]},
        headers=token,
    )
    assert retry.status_code == 202
    assert retry.json()["retry_of"] == original["job_id"]
    assert retry.json()["job_id"] != original["job_id"]

    saved = jobs_client.get(
        f"{BASE}/{original['job_id']}", headers=token
    ).json()
    assert saved["status"] == "cancelled"
    assert saved["cancel_reason"] == "Cancel before execution"


@pytest.mark.parametrize("payload", [
    {"reason": "   "},
    {"reason": "Example", "force_rebuild": "false"},
    {"reason": "Example", "command": "arbitrary command"},
    {"reason": "Example", "snapshot_path": "/arbitrary/path"},
])
def test_unsafe_or_invalid_job_fields_rejected(jobs_client, payload):
    token = headers(jobs_client)
    assert jobs_client.post(
        BASE, json=payload, headers=token
    ).status_code == 422
    assert jobs_client.get(BASE, headers=token).json()["items"] == []


def test_running_cancel_keeps_single_job_guard(jobs_client):
    token = headers(jobs_client)
    job = jobs_client.post(
        BASE, json={"reason": "Running fixture"}, headers=token
    ).json()

    # Simulate a claimed worker job without launching a process.
    with closing(sqlite3.connect(auth.DATABASE)) as database:
        with database:
            database.execute(
                "UPDATE pipeline_runs SET status = 'running', "
                "worker_token_hash = ? WHERE job_id = ?",
                ("private-worker-hash", job["job_id"]),
            )

    response = jobs_client.post(
        f"{BASE}/{job['job_id']}/cancel",
        json={"reason": "Stop running fixture"},
        headers=token,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancel_requested"
    assert body["finished_at"] is None
    assert "worker_token_hash" not in body
    assert "private-worker-hash" not in response.text

    assert jobs_client.post(
        BASE, json={"reason": "Overlapping attempt"}, headers=token
    ).status_code == 409


def test_unknown_job_and_retry_return_404(jobs_client):
    token = headers(jobs_client)
    unknown = str(uuid4())
    assert jobs_client.get(
        f"{BASE}/{unknown}", headers=token
    ).status_code == 404
    assert jobs_client.post(
        BASE,
        json={"reason": "Unknown retry", "retry_of": unknown},
        headers=token,
    ).status_code == 404
    assert jobs_client.get(BASE, headers=token).json()["items"] == []


WORKER_BASE = "/v1/pipeline-worker"
WORKER_SECRET = "temporary-worker-secret-for-tests-only"


def claimed_job(client):
    token = headers(client)
    response = client.post(
        BASE, json={"reason": "Worker fixture"}, headers=token
    )
    assert response.status_code == 202

    response = client.post(
        WORKER_BASE + "/claim",
        json={"worker_token": WORKER_SECRET},
        headers=token,
    )
    assert response.status_code == 200
    job = response.json()["job"]
    worker_headers = {
        **token,
        "X-Pipeline-Worker-Token": WORKER_SECRET,
    }
    return job, token, worker_headers


def test_worker_claim_is_exclusive_and_secret_is_hidden(jobs_client):
    job, token, worker = claimed_job(jobs_client)
    assert job["status"] == "running"
    assert job["started_at"] is not None
    assert "worker_token_hash" not in job

    second = jobs_client.post(
        WORKER_BASE + "/claim",
        json={"worker_token": "another-temporary-worker-secret-123"},
        headers=token,
    )
    assert second.status_code == 200
    assert second.json()["job"] is None

    endpoint = f"{WORKER_BASE}/{job['job_id']}"
    wrong = {**worker, "X-Pipeline-Worker-Token": "incorrect-secret"}
    assert jobs_client.get(endpoint, headers=wrong).status_code == 403

    response = jobs_client.get(endpoint, headers=worker)
    assert response.status_code == 200
    assert WORKER_SECRET not in response.text
    assert "worker_token_hash" not in response.json()


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_non_maintainer_cannot_claim_jobs(jobs_client, role):
    response = jobs_client.post(
        WORKER_BASE + "/claim",
        json={"worker_token": WORKER_SECRET},
        headers=headers(jobs_client, role),
    )
    assert response.status_code == 403


def test_anonymous_worker_claim_rejected(jobs_client):
    assert jobs_client.post(
        WORKER_BASE + "/claim",
        json={"worker_token": WORKER_SECRET},
    ).status_code == 401


def test_ordered_stages_and_success_gate(jobs_client):
    job, token, worker = claimed_job(jobs_client)
    endpoint = f"{WORKER_BASE}/{job['job_id']}"

    assert jobs_client.post(
        endpoint + "/stage-start",
        json={"stage_id": "train"}, headers=worker,
    ).status_code == 409
    assert jobs_client.post(
        endpoint + "/stage-start",
        json={"stage_id": "arbitrary_command"}, headers=worker,
    ).status_code == 422
    assert jobs_client.post(
        endpoint + "/finish",
        json={"status": "succeeded", "summary": {"quality_gate_passed": True}},
        headers=worker,
    ).status_code == 409

    for stage in ("spark_etl", "train", "evaluate"):
        assert jobs_client.post(
            endpoint + "/stage-start",
            json={"stage_id": stage}, headers=worker,
        ).status_code == 200
        assert jobs_client.post(
            endpoint + "/stage-start",
            json={"stage_id": stage}, headers=worker,
        ).status_code == 409
        assert jobs_client.post(
            endpoint + "/stage-finish",
            json={
                "stage_id": stage,
                "status": "reused" if stage == "spark_etl" else "succeeded",
                "elapsed_seconds": 0.1,
                "counts": {},
            },
            headers=worker,
        ).status_code == 200

    assert jobs_client.post(
        endpoint + "/finish",
        json={"status": "succeeded", "summary": {"quality_gate_passed": False}},
        headers=worker,
    ).status_code == 409

    response = jobs_client.post(
        endpoint + "/finish",
        json={"status": "succeeded", "summary": {"quality_gate_passed": True}},
        headers=worker,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["stages"][0]["status"] == "reused"
    assert response.json()["finished_at"] is not None

    assert jobs_client.post(
        endpoint + "/finish",
        json={"status": "succeeded", "summary": {"quality_gate_passed": True}},
        headers=worker,
    ).status_code == 409


def test_worker_acknowledges_cancellation_before_guard_releases(jobs_client):
    job, token, worker = claimed_job(jobs_client)
    endpoint = f"{WORKER_BASE}/{job['job_id']}"

    assert jobs_client.post(
        endpoint + "/stage-start",
        json={"stage_id": "spark_etl"}, headers=worker,
    ).status_code == 200
    assert jobs_client.post(
        f"{BASE}/{job['job_id']}/cancel",
        json={"reason": "Cancellation fixture"}, headers=token,
    ).status_code == 200
    assert jobs_client.post(
        BASE, json={"reason": "Too early"}, headers=token,
    ).status_code == 409

    response = jobs_client.post(
        endpoint + "/finish",
        json={"status": "cancelled"}, headers=worker,
    )
    assert response.status_code == 200
    assert response.json()["stages"][0]["status"] == "cancelled"
    assert all(
        stage["status"] == "skipped"
        for stage in response.json()["stages"][1:]
    )
    assert jobs_client.post(
        BASE, json={"reason": "After worker stopped"}, headers=token,
    ).status_code == 202


def test_failed_stage_prevents_later_execution(jobs_client):
    job, token, worker = claimed_job(jobs_client)
    endpoint = f"{WORKER_BASE}/{job['job_id']}"

    jobs_client.post(
        endpoint + "/stage-start",
        json={"stage_id": "spark_etl"}, headers=worker,
    ).raise_for_status()
    jobs_client.post(
        endpoint + "/stage-finish",
        json={
            "stage_id": "spark_etl",
            "status": "failed",
            "elapsed_seconds": 0.1,
        },
        headers=worker,
    ).raise_for_status()

    assert jobs_client.post(
        endpoint + "/stage-start",
        json={"stage_id": "train"}, headers=worker,
    ).status_code == 409

    response = jobs_client.post(
        endpoint + "/finish",
        json={"status": "failed", "error_code": "stage_failed"},
        headers=worker,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["error_code"] == "stage_failed"
    assert body["stages"][0]["status"] == "failed"
    assert all(stage["status"] == "skipped" for stage in body["stages"][1:])


def test_worker_claim_is_bound_to_authenticated_account(jobs_client):
    job, token, worker = claimed_job(jobs_client)
    auth.create_user("second_maintainer", PASSWORD, "maintainer")
    other = {
        **headers(jobs_client, "second_maintainer"),
        "X-Pipeline-Worker-Token": WORKER_SECRET,
    }
    assert jobs_client.get(
        f"{WORKER_BASE}/{job['job_id']}", headers=other,
    ).status_code == 403
