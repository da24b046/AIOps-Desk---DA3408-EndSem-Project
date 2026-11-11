"""Local ticket prediction API backed by MLflow and SQLite."""

import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.explanation_schema import PredictionExplanation, parse_explanation

from src.metrics import (
    CATEGORY_SCORE, DB_WRITE_FAILURES, PREDICTIONS, PRIORITY_SCORE,
    instrument_model_call, install_metrics,
)

from src.sessions import current_user, initialize_sessions, router as session_router
from src.history import router as history_router
from src.feedback import initialize_feedback, router as feedback_router
from src.reviews import initialize_reviews, router as review_router
from src.pipeline_worker_api import router as pipeline_worker_router

from src.pipeline_jobs import (
    initialize_pipeline_jobs, router as pipeline_router,
)

ROOT = Path(__file__).resolve().parents[1]
POLICY = json.loads(
    (ROOT / "configs/policy.json").read_text(encoding="utf-8")
)
MODEL_URL = os.environ.get(
    "AIOPS_MODEL_URL", "http://127.0.0.1:5001"
).rstrip("/")
DATABASE = ROOT / "state/app/aiops.db"


class TicketInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    subject: str = Field(min_length=1, max_length=5000)
    description: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def check_combined_length(self):
        limit = POLICY["max_combined_text_characters"]
        if len(self.subject) + len(self.description) > limit:
            raise ValueError(f"Combined text must not exceed {limit} characters.")
        return self


class ModelOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    category: str
    category_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    priority: str
    priority_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    model_version: str
    explanation_json: str | None = None


class PredictionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str
    category_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    priority: str
    priority_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    team: str
    needs_review: bool
    review_reasons: list[str]
    explanation: PredictionExplanation | None = None


class PredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prediction_id: str
    result: PredictionResult
    model_version: str
    policy_version: str
    created_at: str
    warnings: list[str]


def connect_database():
    return sqlite3.connect(DATABASE, timeout=3)


@asynccontextmanager
async def lifespan(app):
    DATABASE.parent.mkdir(parents=True, exist_ok=True)

    with closing(connect_database()) as database:
        database.execute("PRAGMA journal_mode=WAL")
        database.execute("""
            CREATE TABLE IF NOT EXISTS predictions (
                prediction_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                model_version TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                redacted_input_json TEXT NOT NULL,
                result_json TEXT NOT NULL
            )
        """)
        columns = {
            row[1] for row in database.execute("PRAGMA table_info(predictions)")
        }
        if "owner_username" not in columns:
            database.execute(
                "ALTER TABLE predictions ADD COLUMN owner_username TEXT"
            )
        database.commit()

    initialize_sessions()
    initialize_feedback()
    initialize_reviews()
    initialize_pipeline_jobs()
    yield


app = FastAPI(
    title="AIOpsDesk API",
    version="0.1.0",
    lifespan=lifespan,
)


@instrument_model_call
def call_model(ticket):
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            response = client.post(
                MODEL_URL + "/invocations",
                json={"dataframe_records": [ticket.model_dump()]},
            )
            response.raise_for_status()

        records = response.json()["predictions"]
        if not isinstance(records, list) or len(records) != 1:
            raise ValueError("Unexpected prediction count.")

        prediction = ModelOutput.model_validate(records[0])

        if prediction.model_version != POLICY["expected_model_version"]:
            raise ValueError("Unexpected model version.")
        if prediction.category not in POLICY["category_to_team"]:
            raise ValueError("Unknown category.")
        if prediction.priority not in POLICY["priority_labels"]:
            raise ValueError("Unknown priority.")

        return prediction

    except httpx.TimeoutException:
        raise HTTPException(504, "Model request timed out.") from None
    except httpx.RequestError:
        raise HTTPException(503, "Model service unavailable.") from None
    except httpx.HTTPStatusError:
        raise HTTPException(502, "Model service returned an error.") from None
    except (ValueError, KeyError, TypeError):
        raise HTTPException(502, "Model response failed validation.") from None


def redact(value):
    return re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
        "[EMAIL]",
        value,
    )


@app.get("/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
def ready():
    try:
        prediction = call_model(TicketInput(
            subject="Service readiness check",
            description="Check that the packaged model can respond.",
        ))
        with closing(connect_database()) as database:
            database.execute("SELECT prediction_id FROM predictions LIMIT 1")
    except (HTTPException, sqlite3.Error):
        raise HTTPException(503, "Model or database is not ready.") from None

    return {
        "status": "ready",
        "model_version": prediction.model_version,
        "policy_version": POLICY["policy_version"],
    }


@app.get("/v1/model-info")
def model_info():
    return {
        "model_version": POLICY["expected_model_version"],
        "policy_version": POLICY["policy_version"],
        "categories": list(POLICY["category_to_team"]),
        "priorities": POLICY["priority_labels"],
        "review_thresholds": POLICY["review_thresholds"],
        "score_note": "Model scores; probability calibration not evaluated.",
    }


@app.post("/v1/predict", response_model=PredictionResponse)
def predict(ticket: TicketInput, user: dict = Depends(current_user)):
    prediction = call_model(ticket)
    reasons = []

    for field, threshold in POLICY["review_thresholds"].items():
        if getattr(prediction, field) < threshold:
            reasons.append(f"low_{field}")

    result = prediction.model_dump(exclude={"model_version", "explanation_json"})
    result.update({
        "explanation": parse_explanation(
            prediction.explanation_json, prediction, POLICY
        ),
        "team": POLICY["category_to_team"][prediction.category],
        "needs_review": bool(reasons),
        "review_reasons": reasons,
    })

    prediction_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    redacted_input = {
        key: redact(value) for key, value in ticket.model_dump().items()
    }

    try:
        with closing(connect_database()) as database:
            with database:
                database.execute(
                    "INSERT INTO predictions "
                    "(prediction_id, created_at, model_version, policy_version, "
                    "redacted_input_json, result_json, owner_username) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        prediction_id,
                        created_at,
                        prediction.model_version,
                        POLICY["policy_version"],
                        json.dumps(redacted_input),
                        json.dumps(result),
                        user["username"],
                    ),
                )
    except sqlite3.Error:
        DB_WRITE_FAILURES.inc()
        raise HTTPException(503, "Could not save the prediction.") from None

    PREDICTIONS.labels(
        category=prediction.category,
        priority=prediction.priority,
        needs_review=str(result["needs_review"]).lower(),
    ).inc()
    CATEGORY_SCORE.observe(prediction.category_score)
    PRIORITY_SCORE.observe(prediction.priority_score)

    return {
        "prediction_id": prediction_id,
        "result": result,
        "model_version": prediction.model_version,
        "policy_version": POLICY["policy_version"],
        "created_at": created_at,
        "warnings": reasons,
    }


app.include_router(session_router)

app.include_router(history_router)

app.include_router(feedback_router)

app.include_router(review_router)

app.include_router(pipeline_router)

app.include_router(pipeline_worker_router)

install_metrics(
    app,
    model_version=POLICY["expected_model_version"],
    policy_version=POLICY["policy_version"],
)
