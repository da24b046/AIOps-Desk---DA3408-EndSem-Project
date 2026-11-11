# AIOpsDesk - Low-Level Design

REST interfaces, data contracts and execution states

Reviewed for submission using the recorded 2026-11-11 measurements and completed handover checks. Evidence paths and scope are consolidated in the root report.md; document hashes are recorded in reports/documentation_check.json.

## 1. Interface source of truth

The endpoint inventory below is generated from the FastAPI schema captured during implementation. Interactive documentation is at http://127.0.0.1:8000/docs. The public error body uses FastAPI's actual detail field (a message or validation-error list); the blueprint's proposed request_id/error envelope was not implemented.

The browser calls only its configurable API_BASE_URL, normally /api. Nginx strips that prefix and forwards requests to api:8000. The API makes private model calls to http://model:5001/invocations. The browser never loads classifier files.

## 2. Endpoint inventory

| Method | Path | Body schema | Access | Responses |
| --- | --- | --- | --- | --- |
| GET | /health/live | None | Public | 200 |
| GET | /health/ready | None | Public | 200 |
| GET | /v1/model-info | None | Public | 200 |
| POST | /v1/predict | TicketInput | Bearer | 200, 422 |
| GET | /v1/session | None | Bearer | 200 |
| POST | /v1/session | LoginInput | Public | 200, 422 |
| DELETE | /v1/session | None | Bearer | 204 |
| GET | /v1/predictions | None | Bearer | 200, 422 |
| GET | /v1/predictions/{prediction_id} | None | Bearer | 200, 422 |
| POST | /v1/feedback | FeedbackInput | Bearer | 201, 422 |
| GET | /v1/feedback | None | Bearer | 200, 422 |
| POST | /v1/feedback/{feedback_id}/review | ReviewInput | Bearer | 200, 422 |
| GET | /v1/feedback/{feedback_id}/review | None | Bearer | 200, 422 |
| POST | /v1/pipeline-runs | JobInput | Bearer | 202, 422 |
| GET | /v1/pipeline-runs | None | Bearer | 200, 422 |
| GET | /v1/pipeline-runs/{job_id} | None | Bearer | 200, 422 |
| POST | /v1/pipeline-runs/{job_id}/cancel | CancelInput | Bearer | 200, 422 |
| POST | /v1/pipeline-worker/claim | ClaimInput | Bearer | 200, 422 |
| GET | /v1/pipeline-worker/{job_id} | None | Bearer | 200, 422 |
| POST | /v1/pipeline-worker/{job_id}/stage-start | StageStart | Bearer | 200, 422 |
| POST | /v1/pipeline-worker/{job_id}/stage-finish | StageFinish | Bearer | 200, 422 |
| POST | /v1/pipeline-worker/{job_id}/finish | JobFinish | Bearer | 200, 422 |

Public endpoints cover health, safe model information and the local metrics scrape. Authenticated prediction/history are role-aware. Feedback submission is operator/maintainer; feedback review and all pipeline/worker routes are maintainer-only. Worker control additionally checks a temporary claim secret and the authenticated account.

## 3. Prediction contract

Example request, containing only creation-time text:

```json
{
  "subject": "Cannot connect to office Wi-Fi",
  "description": "My laptop cannot connect. Other employees can connect normally."
}
```

TicketInput forbids extra fields, strips outer whitespace, requires both strings and bounds their combined length to 5000 characters. Pydantic rejects missing/empty fields. The response contains prediction_id, result, model_version, policy_version, created_at and warnings. Result contains category, priority, finite scores in [0,1], team, needs_review, review_reasons and explanation.

The model's tabular response carries explanation_json internally. FastAPI parses a bounded object with available/unavailable status and category/priority explanations. Each available target contains predicted/alternative classes, up to five signed contributions, intercept, omitted-term sum, decision margin and a cautionary note. The parser verifies labels and margin reconstruction; a rejected explanation becomes unavailable independently of core inference.

## 4. Authentication, history and feedback

POST /v1/session returns a random bearer token; only its SHA-256 digest is stored. DELETE invalidates that session. Refreshing the UI clears its in-memory token and requires sign-in. Viewer history is owner-filtered; operators and maintainers may inspect all records. History uses descending SQLite rowid cursors and limit <=100. Cross-owner viewer lookup returns 404.

Feedback requires a prediction UUID, at least one supported corrected label, a reason and label_source. Unreviewed labels are omitted rather than copied from the model. Operator review is distinguished from synthetic_demo. A maintainer decision is approved or rejected; self-review is forbidden and a second decision returns conflict. Reviewed feedback does not update the original prediction.

## 5. Database entities and transactions

| Entity | Stored information |
| --- | --- |
| predictions | UUID, owner, redacted input/result JSON, model/policy versions and UTC creation time |
| users / sessions | Argon2 password hashes; hashed random bearer tokens with one-hour expiry |
| feedback | Prediction reference, independently reviewed category/priority, reason, author, source and status |
| feedback_reviews | One immutable decision per feedback ID, reviewer, reason and timestamp |
| pipeline_runs | Job ID/status, config version, reason, requester, retry link, timestamps, stages/summary JSON, worker claim hash and error code |

SQLite connections are bounded/closed, SQL values are parameterized, and application storage uses WAL. A prediction is saved before success is returned. A write failure yields a controlled 503. Feedback decisions and job claims use transactions. The one_active_pipeline partial unique index allows at most one queued/running/cancel_requested job.

## 6. Pipeline state machine

queued -> running -> succeeded / failed / cancelled / interrupted.

Running cancellation first sets cancel_requested. It stays active until the worker stops its command group and acknowledges a terminal outcome. Cancelling a queued job immediately sets cancelled and marks stages skipped. Retry creates a new UUID referencing retry_of; previous history remains unchanged.

Stage order is spark_etl -> train -> evaluate. A stage must be pending with all predecessors succeeded/reused before it starts. Completion records elapsed seconds and bounded count fields. A successful job requires all stages succeeded/reused and quality_gate_passed=true. Worker secrets are excluded from serialized history.

The host worker holds a checkout-local file lock. It accepts no arbitrary commands from the API. DVC status --json identifies clean stages; otherwise the worker invokes dvc repro --single-item --force --no-run-cache for that fixed stage. Subprocess stdin is closed, logs are bounded to about 1 MiB per command, and cancellation/timeout stops the process group. The maximum configured stage duration is 300 seconds.

## 7. Snapshot and release interfaces

Snapshot export is a CLI operation, not a web endpoint. The explicit --database backup option reads SQLite in read-only mode and verifies the maintainer against that backup. Approved events are joined with review audit records; the newest approved label per prediction/target wins. Rows are sorted and content-addressed. Reused content keeps its original manifest and cutoff.

Release quality decisions, image preservation and Compose switching are scripts/configuration files. There is no releases API. The synthetic feedback candidate was rejected by the quality policy; a separately labelled stop/start exercise verified deployment mechanics and rollback. The explanation bundle changes serving capabilities while preserving the fitted candidate-001 models and policy-001.

## 8. Error and failure behaviour

| Condition | Observed contract |
| --- | --- |
| Missing/invalid login | 401 |
| Insufficient role / worker claim mismatch | 403 |
| Unknown record or hidden viewer record | 404 |
| Active-job overlap or repeated review/invalid state transition | 409 |
| Invalid request schema | 422 |
| Model HTTP/response validation failure | 502 |
| Unavailable model/storage or failed readiness | 503 |
| Model transport timeout | 504 |
| Explanation invalid | Prediction retained with explanation unavailable |
| Job process failure/timeout | Terminal error code and skipped downstream stages; serving model unchanged |

Unexpected process termination or prolonged API communication loss can retain an active job lock; no automatic stale-job reset is advertised. Worker errors are exposed as bounded codes; local logs provide diagnostics. Default Uvicorn access logs and pipeline logs are present; a complete structured request-correlation logging system is deferred.

## 9. Source map

src/api.py orchestrates prediction; auth.py and sessions.py implement identity; history.py, feedback.py and reviews.py implement audit workflows; snapshots.py exports approved labels; pipeline_jobs.py and pipeline_worker_api.py manage jobs; scripts/pipeline_worker.py executes them; linear_explanations.py and explanation_schema.py implement explainability. Frontend components consume these REST contracts. The running API exposes full schemas and required fields at /openapi.json and /docs.
