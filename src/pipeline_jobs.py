"""Persistent, maintainer-only pipeline jobs with a single active-job guard."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, StrictBool

import src.auth as auth
from src.sessions import require_roles

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads(
    (ROOT / "configs/pipeline_console.json").read_text(encoding="utf-8")
)
STAGES = [stage["id"] for stage in CONFIG["stages"]]
TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
maintainer = require_roles("maintainer")
router = APIRouter(prefix="/v1/pipeline-runs", tags=["Pipeline jobs"])


def now():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def database(*, write=False):
    connection = None
    try:
        connection = sqlite3.connect(auth.DATABASE, timeout=3)
        connection.row_factory = sqlite3.Row
        if write:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        if write:
            connection.commit()
    except sqlite3.Error:
        raise HTTPException(503, "Pipeline job storage unavailable.") from None
    finally:
        if connection is not None:
            if connection.in_transaction:
                connection.rollback()
            connection.close()


def initialize_pipeline_jobs():
    with database(write=True) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                job_id TEXT PRIMARY KEY,
                config_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN (
                    'queued', 'running', 'cancel_requested',
                    'succeeded', 'failed', 'cancelled', 'interrupted'
                )),
                requested_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                force_rebuild INTEGER NOT NULL,
                retry_of TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                updated_at TEXT NOT NULL,
                cancel_reason TEXT,
                worker_token_hash TEXT,
                worker_username TEXT,
                stages_json TEXT NOT NULL,
                summary_json TEXT NOT NULL DEFAULT '{}',
                error_code TEXT
            )
        """)
        connection.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_pipeline
            ON pipeline_runs ((1))
            WHERE status IN ('queued', 'running', 'cancel_requested')
        """)


def find_job(connection, job_id):
    row = connection.execute(
        "SELECT * FROM pipeline_runs WHERE job_id = ?", (str(job_id),)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "Pipeline job not found.")
    return row


def serialize(row):
    result = {
        key: row[key] for key in (
            "job_id", "config_version", "status", "requested_by",
            "reason", "retry_of", "created_at", "started_at",
            "finished_at", "updated_at", "cancel_reason", "error_code",
        )
    }
    result.update({
        "force_rebuild": bool(row["force_rebuild"]),
        "stages": json.loads(row["stages_json"]),
        "summary": json.loads(row["summary_json"]),
        "deployment_enabled": False,
    })
    return result


class JobInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=200)
    force_rebuild: StrictBool = False
    retry_of: UUID | None = None


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=200)


@router.post("", status_code=202)
def create_job(payload: JobInput, user: dict = Depends(maintainer)):
    job_id = str(uuid4())
    timestamp = now()
    stages = [
        {
            "id": stage["id"],
            "label": stage["label"],
            "status": "pending",
            "started_at": None,
            "finished_at": None,
            "elapsed_seconds": None,
            "counts": {},
        }
        for stage in CONFIG["stages"]
    ]

    with database(write=True) as connection:
        active = connection.execute("""
            SELECT job_id FROM pipeline_runs
            WHERE status IN ('queued', 'running', 'cancel_requested')
        """).fetchone()
        if active is not None:
            raise HTTPException(409, "Another pipeline job is active.")

        if payload.retry_of is not None:
            previous = find_job(connection, payload.retry_of)
            if previous["status"] not in TERMINAL:
                raise HTTPException(409, "Only a finished job can be retried.")

        connection.execute("""
            INSERT INTO pipeline_runs (
                job_id, config_version, status, requested_by, reason,
                force_rebuild, retry_of, created_at, updated_at, stages_json
            ) VALUES (?, ?, 'queued', ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id, CONFIG["config_version"], user["username"], payload.reason,
            int(payload.force_rebuild),
            str(payload.retry_of) if payload.retry_of else None,
            timestamp, timestamp, json.dumps(stages),
        ))
        result = serialize(find_job(connection, job_id))
    return result


@router.get("")
def list_jobs(
    limit: int = Query(default=20, ge=1, le=50),
    user: dict = Depends(maintainer),
):
    with database() as connection:
        rows = connection.execute(
            "SELECT * FROM pipeline_runs ORDER BY rowid DESC LIMIT ?", (limit,)
        ).fetchall()
        return {"items": [serialize(row) for row in rows]}


@router.get("/{job_id}")
def get_job(job_id: UUID, user: dict = Depends(maintainer)):
    with database() as connection:
        return serialize(find_job(connection, job_id))


@router.post("/{job_id}/cancel")
def cancel_job(
    job_id: UUID,
    payload: CancelInput,
    user: dict = Depends(maintainer),
):
    with database(write=True) as connection:
        row = find_job(connection, job_id)
        if row["status"] in TERMINAL:
            raise HTTPException(409, "Pipeline job is already finished.")

        timestamp = now()
        queued = row["status"] == "queued"
        status = "cancelled" if queued else "cancel_requested"
        stages = json.loads(row["stages_json"])

        if queued:
            for stage in stages:
                stage["status"] = "skipped"

        connection.execute("""
            UPDATE pipeline_runs
            SET status = ?, cancel_reason = ?, updated_at = ?,
                finished_at = ?, stages_json = ?
            WHERE job_id = ?
        """, (
            status, payload.reason, timestamp,
            timestamp if queued else None,
            json.dumps(stages), str(job_id),
        ))
        return serialize(find_job(connection, job_id))
