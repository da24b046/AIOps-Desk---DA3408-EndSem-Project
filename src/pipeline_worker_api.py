"""Authenticated worker claims and ordered pipeline stage transitions."""

import hashlib
import json
import secrets
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from src.pipeline_jobs import (
    CONFIG, database, find_job, maintainer, now, serialize,
)

router = APIRouter(prefix="/v1/pipeline-worker", tags=["Pipeline worker"])
StageID = Literal["spark_etl", "train", "evaluate"]
ErrorCode = Literal[
    "stage_failed", "stage_timeout", "worker_interrupted",
    "worker_connection_lost", "quality_gate_failed",
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClaimInput(Input):
    worker_token: SecretStr = Field(min_length=32, max_length=128)


class StageStart(Input):
    stage_id: StageID


class StageFinish(StageStart):
    status: Literal["succeeded", "reused", "failed", "cancelled"]
    elapsed_seconds: float = Field(ge=0, le=3600, allow_inf_nan=False)
    counts: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def check_counts(self):
        allowed = {
            "input_rows", "retained_rows", "rejected_rows",
            "train_rows", "validation_rows",
        }
        if not set(self.counts).issubset(allowed):
            raise ValueError("Unsupported count field.")
        if any(value < 0 or value > 1000000 for value in self.counts.values()):
            raise ValueError("Count outside supported range.")
        return self


class JobFinish(Input):
    status: Literal["succeeded", "failed", "cancelled", "interrupted"]
    error_code: ErrorCode | None = None
    summary: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def bound_summary(self):
        if len(json.dumps(self.summary, allow_nan=False)) > 8000:
            raise ValueError("Summary exceeds the size limit.")
        return self


def owned_job(connection, job_id, user, token):
    row = find_job(connection, job_id)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    if (
        row["worker_username"] != user["username"]
        or not row["worker_token_hash"]
        or not secrets.compare_digest(row["worker_token_hash"], digest)
    ):
        raise HTTPException(403, "Worker claim does not match this job.")
    return row


def active_job(row):
    if row["status"] not in ("running", "cancel_requested"):
        raise HTTPException(409, "Worker job is already finished.")


def stages_of(row):
    return json.loads(row["stages_json"])


@router.post("/claim")
def claim(payload: ClaimInput, user: dict = Depends(maintainer)):
    digest = hashlib.sha256(
        payload.worker_token.get_secret_value().encode("utf-8")
    ).hexdigest()

    with database(write=True) as connection:
        row = connection.execute(
            "SELECT * FROM pipeline_runs WHERE status = 'queued' "
            "ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is None:
            return {"job": None, "config": CONFIG}

        timestamp = now()
        connection.execute("""
            UPDATE pipeline_runs
            SET status = 'running', started_at = ?, updated_at = ?,
                worker_token_hash = ?, worker_username = ?
            WHERE job_id = ? AND status = 'queued'
        """, (
            timestamp, timestamp, digest, user["username"], row["job_id"],
        ))
        return {
            "job": serialize(find_job(connection, row["job_id"])),
            "config": CONFIG,
        }


@router.get("/{job_id}")
def worker_status(
    job_id: UUID,
    user: dict = Depends(maintainer),
    token: str = Header(alias="X-Pipeline-Worker-Token", max_length=128),
):
    with database() as connection:
        return serialize(owned_job(connection, job_id, user, token))


@router.post("/{job_id}/stage-start")
def stage_start(
    job_id: UUID,
    payload: StageStart,
    user: dict = Depends(maintainer),
    token: str = Header(alias="X-Pipeline-Worker-Token", max_length=128),
):
    with database(write=True) as connection:
        row = owned_job(connection, job_id, user, token)
        active_job(row)
        if row["status"] == "cancel_requested":
            raise HTTPException(409, "Cancellation requested.")

        stages = stages_of(row)
        index = next(
            i for i, stage in enumerate(stages)
            if stage["id"] == payload.stage_id
        )
        if stages[index]["status"] != "pending" or any(
            stage["status"] not in ("succeeded", "reused")
            for stage in stages[:index]
        ):
            raise HTTPException(409, "Invalid stage order or repeated start.")

        timestamp = now()
        stages[index].update(status="running", started_at=timestamp)
        connection.execute(
            "UPDATE pipeline_runs SET stages_json = ?, updated_at = ? "
            "WHERE job_id = ?",
            (json.dumps(stages), timestamp, str(job_id)),
        )
        return serialize(find_job(connection, job_id))


@router.post("/{job_id}/stage-finish")
def stage_finish(
    job_id: UUID,
    payload: StageFinish,
    user: dict = Depends(maintainer),
    token: str = Header(alias="X-Pipeline-Worker-Token", max_length=128),
):
    with database(write=True) as connection:
        row = owned_job(connection, job_id, user, token)
        active_job(row)
        stages = stages_of(row)
        stage = next(s for s in stages if s["id"] == payload.stage_id)
        if stage["status"] != "running":
            raise HTTPException(409, "Stage is not running.")

        timestamp = now()
        stage.update(
            status=payload.status,
            finished_at=timestamp,
            elapsed_seconds=payload.elapsed_seconds,
            counts=payload.counts,
        )
        connection.execute(
            "UPDATE pipeline_runs SET stages_json = ?, updated_at = ? "
            "WHERE job_id = ?",
            (json.dumps(stages), timestamp, str(job_id)),
        )
        return serialize(find_job(connection, job_id))


@router.post("/{job_id}/finish")
def finish(
    job_id: UUID,
    payload: JobFinish,
    user: dict = Depends(maintainer),
    token: str = Header(alias="X-Pipeline-Worker-Token", max_length=128),
):
    with database(write=True) as connection:
        row = owned_job(connection, job_id, user, token)
        active_job(row)
        stages = stages_of(row)

        if payload.status == "succeeded":
            if (
                row["status"] == "cancel_requested"
                or not all(
                    stage["status"] in ("succeeded", "reused")
                    for stage in stages
                )
                or payload.summary.get("quality_gate_passed") is not True
                or payload.error_code is not None
            ):
                raise HTTPException(409, "Successful completion checks failed.")

        timestamp = now()
        for stage in stages:
            if stage["status"] == "pending":
                stage["status"] = "skipped"
            elif stage["status"] == "running":
                stage["status"] = (
                    "failed" if payload.status == "failed" else payload.status
                )
                stage["finished_at"] = timestamp
                stage["elapsed_seconds"] = max(
                    0.0,
                    (
                        datetime.fromisoformat(timestamp)
                        - datetime.fromisoformat(stage["started_at"])
                    ).total_seconds(),
                )

        connection.execute("""
            UPDATE pipeline_runs
            SET status = ?, finished_at = ?, updated_at = ?,
                stages_json = ?, summary_json = ?, error_code = ?
            WHERE job_id = ?
        """, (
            payload.status, timestamp, timestamp,
            json.dumps(stages), json.dumps(payload.summary),
            payload.error_code, str(job_id),
        ))
        return serialize(find_job(connection, job_id))
