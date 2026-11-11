"""Role-protected feedback submission and history."""

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.auth import DATABASE
from src.sessions import require_roles

router = APIRouter(prefix="/v1", tags=["Feedback"])
feedback_user = require_roles("operator", "maintainer")


class FeedbackInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    prediction_id: UUID
    category: Literal["Software", "Account", "Network", "Security"] | None = None
    priority: Literal["Medium", "High"] | None = None
    reason: str = Field(min_length=1, max_length=500)
    label_source: Literal["operator_review", "synthetic_demo"] = "operator_review"

    @model_validator(mode="after")
    def require_label(self):
        if self.category is None and self.priority is None:
            raise ValueError("Provide a category or priority.")
        return self


def connect():
    database = sqlite3.connect(DATABASE, timeout=3)
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys=ON")
    return database


def initialize_feedback():
    with closing(connect()) as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                prediction_id TEXT NOT NULL REFERENCES predictions(prediction_id),
                labels_json TEXT NOT NULL,
                reason TEXT NOT NULL,
                author_username TEXT NOT NULL REFERENCES users(username),
                label_source TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending', 'approved', 'rejected')),
                created_at TEXT NOT NULL
            )
        """)
        database.commit()


def serialize(row):
    return {
        "feedback_id": row["feedback_id"],
        "prediction_id": row["prediction_id"],
        "labels": json.loads(row["labels_json"]),
        "reason": row["reason"],
        "author_username": row["author_username"],
        "label_source": row["label_source"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


@router.post("/feedback", status_code=201)
def submit_feedback(
    feedback: FeedbackInput,
    user: dict = Depends(feedback_user),
):
    feedback_id = str(uuid4())
    created_at = datetime.now(timezone.utc).isoformat()
    labels = feedback.model_dump(
        include={"category", "priority"}, exclude_none=True
    )

    try:
        with closing(connect()) as database:
            with database:
                prediction = database.execute(
                    "SELECT prediction_id FROM predictions WHERE prediction_id = ?",
                    (str(feedback.prediction_id),),
                ).fetchone()
                if prediction is None:
                    raise HTTPException(404, "Prediction not found.")

                database.execute(
                    """
                    INSERT INTO feedback
                    (feedback_id, prediction_id, labels_json, reason,
                     author_username, label_source, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        feedback_id,
                        str(feedback.prediction_id),
                        json.dumps(labels),
                        feedback.reason,
                        user["username"],
                        feedback.label_source,
                        created_at,
                    ),
                )
                row = database.execute(
                    "SELECT * FROM feedback WHERE feedback_id = ?",
                    (feedback_id,),
                ).fetchone()
    except sqlite3.Error:
        raise HTTPException(503, "Could not save feedback.") from None

    return serialize(row)


@router.get("/feedback")
def list_feedback(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1),
    user: dict = Depends(feedback_user),
):
    query = "SELECT rowid AS cursor_id, * FROM feedback WHERE 1=1"
    parameters = []

    if user["role"] == "operator":
        query += " AND author_username = ?"
        parameters.append(user["username"])

    if cursor is not None:
        query += " AND rowid < ?"
        parameters.append(cursor)

    query += " ORDER BY rowid DESC LIMIT ?"
    parameters.append(limit + 1)

    try:
        with closing(connect()) as database:
            rows = database.execute(query, parameters).fetchall()
    except sqlite3.Error:
        raise HTTPException(503, "Feedback history unavailable.") from None

    visible = rows[:limit]
    return {
        "items": [serialize(row) for row in visible],
        "next_cursor": (
            visible[-1]["cursor_id"] if len(rows) > limit else None
        ),
    }
