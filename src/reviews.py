"""Maintainer feedback review with an immutable decision record."""

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

import sqlite3
from contextlib import closing

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.feedback import connect, feedback_user
from src.sessions import require_roles

router = APIRouter(prefix="/v1", tags=["Feedback review"])


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=1, max_length=500)


def initialize_reviews():
    with closing(connect()) as database:
        database.execute("""
            CREATE TABLE IF NOT EXISTS feedback_reviews (
                review_id TEXT PRIMARY KEY,
                feedback_id TEXT NOT NULL UNIQUE REFERENCES feedback(feedback_id),
                decision TEXT NOT NULL
                    CHECK(decision IN ('approved', 'rejected')),
                reviewer_username TEXT NOT NULL REFERENCES users(username),
                reason TEXT NOT NULL,
                reviewed_at TEXT NOT NULL
            )
        """)
        database.commit()


@router.post("/feedback/{feedback_id}/review")
def review_feedback(
    feedback_id: UUID,
    review: ReviewInput,
    user: dict = Depends(require_roles("maintainer")),
):
    record = {
        "review_id": str(uuid4()),
        "feedback_id": str(feedback_id),
        "decision": review.decision,
        "reviewer_username": user["username"],
        "reason": review.reason,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        with closing(connect()) as database:
            with database:
                database.execute("BEGIN IMMEDIATE")
                feedback = database.execute(
                    "SELECT * FROM feedback WHERE feedback_id = ?",
                    (str(feedback_id),),
                ).fetchone()

                if feedback is None:
                    raise HTTPException(404, "Feedback not found.")
                if feedback["status"] != "pending":
                    raise HTTPException(409, "Feedback already reviewed.")
                if feedback["author_username"] == user["username"]:
                    raise HTTPException(403, "Cannot review your own feedback.")

                database.execute(
                    """
                    INSERT INTO feedback_reviews
                    (review_id, feedback_id, decision, reviewer_username,
                     reason, reviewed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    tuple(record.values()),
                )
                database.execute(
                    "UPDATE feedback SET status = ? WHERE feedback_id = ?",
                    (review.decision, str(feedback_id)),
                )

    except sqlite3.Error:
        raise HTTPException(503, "Could not save review.") from None

    return record


@router.get("/feedback/{feedback_id}/review")
def get_review(
    feedback_id: UUID,
    user: dict = Depends(feedback_user),
):
    query = """
        SELECT feedback_reviews.*
        FROM feedback_reviews
        JOIN feedback ON feedback.feedback_id = feedback_reviews.feedback_id
        WHERE feedback_reviews.feedback_id = ?
    """
    parameters = [str(feedback_id)]

    if user["role"] == "operator":
        query += " AND feedback.author_username = ?"
        parameters.append(user["username"])

    try:
        with closing(connect()) as database:
            row = database.execute(query, parameters).fetchone()
    except sqlite3.Error:
        raise HTTPException(503, "Review history unavailable.") from None

    if row is None:
        raise HTTPException(404, "Review not found.")
    return dict(row)
