"""API integration and fault tests using isolated databases."""

import json
import sqlite3
from contextlib import closing
from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import src.api as api
import src.auth as auth
import src.feedback as feedback
import src.history as history
import src.sessions as sessions

# This password belongs only to disposable test accounts.
TEST_PASSWORD = "temporary-test-password"
TICKET = {
    "subject": "Software access problem",
    "description": "Cannot open the application. Contact demo@example.test.",
}


def model_result():
    return api.ModelOutput(
        category="Software",
        category_score=0.34,
        priority="Medium",
        priority_score=0.61,
        model_version=api.POLICY["expected_model_version"],
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    database_path = tmp_path / "test.db"

    for module in (api, auth, feedback, history, sessions):
        monkeypatch.setattr(module, "DATABASE", database_path)

    monkeypatch.setattr(api, "call_model", lambda ticket: model_result())

    with TestClient(api.app) as test_client:
        for role in ("viewer", "operator", "maintainer"):
            auth.create_user(role, TEST_PASSWORD, role)
        yield test_client


def login(client, role):
    response = client.post(
        "/v1/session",
        json={"username": role, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return {
        "Authorization": "Bearer " + response.json()["access_token"]
    }


def test_anonymous_prediction_rejected(client):
    assert client.post("/v1/predict", json=TICKET).status_code == 401


def test_prediction_persisted_redacted_and_flagged(client):
    response = client.post(
        "/v1/predict", json=TICKET, headers=login(client, "operator")
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["needs_review"] is True
    assert body["result"]["team"] == "Application Support"

    with closing(sqlite3.connect(api.DATABASE)) as database:
        row = database.execute(
            "SELECT owner_username, redacted_input_json, result_json "
            "FROM predictions WHERE prediction_id = ?",
            (body["prediction_id"],),
        ).fetchone()

    assert row[0] == "operator"
    assert json.loads(row[1])["description"] == (
        TICKET["description"].replace("demo@example.test", "[EMAIL]")
    )
    assert json.loads(row[2]) == body["result"]


@pytest.mark.parametrize("payload", [
    {"subject": "Help"},
    {"subject": "   ", "description": "Help"},
    {**TICKET, "category": "Software"},
    {"subject": "x", "description": "x" * 5000},
])
def test_invalid_input_creates_no_prediction(client, payload):
    response = client.post(
        "/v1/predict", json=payload, headers=login(client, "operator")
    )
    assert response.status_code == 422
    with closing(sqlite3.connect(api.DATABASE)) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM predictions"
        ).fetchone()[0] == 0


def test_feedback_review_permissions_and_single_decision(client):
    operator = login(client, "operator")
    viewer = login(client, "viewer")
    maintainer = login(client, "maintainer")

    prediction = client.post(
        "/v1/predict", json=TICKET, headers=operator
    ).json()
    payload = {
        "prediction_id": prediction["prediction_id"],
        "category": "Network",
        "reason": "Synthetic test correction.",
        "label_source": "synthetic_demo",
    }

    assert client.post(
        "/v1/feedback", json=payload, headers=viewer
    ).status_code == 403

    response = client.post("/v1/feedback", json=payload, headers=operator)
    assert response.status_code == 201
    endpoint = f"/v1/feedback/{response.json()['feedback_id']}/review"
    decision = {"decision": "approved", "reason": "Test review."}

    assert client.post(
        endpoint, json=decision, headers=operator
    ).status_code == 403
    assert client.post(
        endpoint, json=decision, headers=maintainer
    ).status_code == 200
    assert client.post(
        endpoint, json=decision, headers=maintainer
    ).status_code == 409

    with closing(sqlite3.connect(api.DATABASE)) as database:
        assert database.execute(
            "SELECT COUNT(*) FROM feedback_reviews"
        ).fetchone()[0] == 1

    saved = client.get(
        f"/v1/predictions/{prediction['prediction_id']}",
        headers=operator,
    ).json()
    assert saved["result"] == prediction["result"]


def test_self_review_forbidden(client):
    maintainer = login(client, "maintainer")
    prediction = client.post(
        "/v1/predict", json=TICKET, headers=maintainer
    ).json()
    response = client.post(
        "/v1/feedback",
        json={
            "prediction_id": prediction["prediction_id"],
            "category": "Network",
            "reason": "Synthetic self-review test.",
            "label_source": "synthetic_demo",
        },
        headers=maintainer,
    )
    assert response.status_code == 201

    response = client.post(
        f"/v1/feedback/{response.json()['feedback_id']}/review",
        json={"decision": "approved", "reason": "Self-review attempt."},
        headers=maintainer,
    )
    assert response.status_code == 403


def test_viewer_cannot_read_another_users_prediction(client):
    operator = login(client, "operator")
    viewer = login(client, "viewer")
    prediction = client.post(
        "/v1/predict", json=TICKET, headers=operator
    ).json()

    assert client.get(
        f"/v1/predictions/{prediction['prediction_id']}",
        headers=viewer,
    ).status_code == 404


def test_model_timeout_translated_to_504():
    with patch("src.api.httpx.Client") as mocked:
        mocked.return_value.__enter__.return_value.post.side_effect = (
            httpx.ReadTimeout("Simulated timeout")
        )
        with pytest.raises(HTTPException) as error:
            api.call_model(api.TicketInput(**TICKET))
    assert error.value.status_code == 504


def test_wrong_model_version_rejected():
    output = model_result().model_dump()
    output["model_version"] = "unexpected-version"
    response = httpx.Response(
        200,
        json={"predictions": [output]},
        request=httpx.Request("POST", "http://model/invocations"),
    )

    with patch("src.api.httpx.Client") as mocked:
        mocked.return_value.__enter__.return_value.post.return_value = response
        with pytest.raises(HTTPException) as error:
            api.call_model(api.TicketInput(**TICKET))
    assert error.value.status_code == 502


def test_failed_database_write_does_not_return_success(client, monkeypatch):
    operator = login(client, "operator")

    def fail_connection():
        raise sqlite3.OperationalError("Simulated database failure")

    monkeypatch.setattr(api, "connect_database", fail_connection)
    response = client.post("/v1/predict", json=TICKET, headers=operator)
    assert response.status_code == 503
    assert "prediction_id" not in response.json()
