"""Authenticated prediction history with ownership filtering."""

import json
import sqlite3
from contextlib import closing
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from src.auth import DATABASE
from src.sessions import current_user

router = APIRouter(prefix="/v1", tags=["Prediction history"])


def serialize(row):
    return {
        "prediction_id": row["prediction_id"],
        "owner_username": row["owner_username"],
        "created_at": row["created_at"],
        "model_version": row["model_version"],
        "policy_version": row["policy_version"],
        "redacted_input": json.loads(row["redacted_input_json"]),
        "result": json.loads(row["result_json"]),
    }


def ownership_filter(user):
    if user["role"] == "viewer":
        return " AND owner_username = ?", [user["username"]]
    if user["role"] in ("operator", "maintainer"):
        return "", []
    raise HTTPException(403, "This role cannot inspect predictions.")


@router.get("/predictions")
def list_predictions(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: int | None = Query(default=None, ge=1),
    user: dict = Depends(current_user),
):
    restriction, parameters = ownership_filter(user)
    query = (
        "SELECT rowid AS cursor_id, * FROM predictions WHERE 1=1"
        + restriction
    )

    if cursor is not None:
        query += " AND rowid < ?"
        parameters.append(cursor)

    query += " ORDER BY rowid DESC LIMIT ?"
    parameters.append(limit + 1)

    try:
        with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
            database.row_factory = sqlite3.Row
            rows = database.execute(query, parameters).fetchall()
    except sqlite3.Error:
        raise HTTPException(503, "Prediction history unavailable.") from None

    visible = rows[:limit]
    next_cursor = (
        visible[-1]["cursor_id"] if len(rows) > limit else None
    )

    return {
        "items": [serialize(row) for row in visible],
        "next_cursor": next_cursor,
    }


@router.get("/predictions/{prediction_id}")
def get_prediction(
    prediction_id: UUID,
    user: dict = Depends(current_user),
):
    restriction, parameters = ownership_filter(user)
    query = (
        "SELECT * FROM predictions WHERE prediction_id = ?"
        + restriction
    )

    try:
        with closing(sqlite3.connect(DATABASE, timeout=3)) as database:
            database.row_factory = sqlite3.Row
            row = database.execute(
                query, [str(prediction_id), *parameters]
            ).fetchone()
    except sqlite3.Error:
        raise HTTPException(503, "Prediction history unavailable.") from None

    if row is None:
        raise HTTPException(404, "Prediction not found.")

    return serialize(row)
