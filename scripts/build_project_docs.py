"""Build evidence-based project documentation without running training or tests.

Usage: python scripts/build_project_docs.py --repo . --out docs
Documentation dependency: reportlab==4.4.9, installed in a separate docs venv.
"""

import argparse
import hashlib
import html
import json
import math
import re
import subprocess
import textwrap
from pathlib import Path
from xml.etree import ElementTree

from reportlab import Version as reportlab_version
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    CondPageBreak, Flowable, LongTable, Paragraph, Preformatted,
    SimpleDocTemplate, Spacer, TableStyle,
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def table(headers, rows):
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(str(v).replace("|", "/").replace("\n", " ") for v in row) + " |" for row in rows),
    ])


def contents(root):
    final = read_json(root, "reports/final_test_evaluation.json")
    perf = read_json(root, "reports/performance_check.json")
    policy = read_json(root, "configs/policy.json")
    selected = read_json(root, "configs/selected_models.json")
    source = read_json(root, "data/metadata/source.json")
    prepared = read_json(root, "reports/data_preparation.json")
    split = read_json(root, "reports/data_splits.json")
    ci = read_json(root, "reports/ci_latest.json")
    drift = read_json(root, "reports/drift_recent.json")
    monitor = read_json(root, "reports/monitoring_coverage_check.json")
    promotion = read_json(root, "reports/promotion_decision.json")
    feedback = read_json(root, "reports/feedback_candidate_metrics.json")
    kserve = read_json(root, "reports/kserve_check.json")
    project = read_json(root, "reports/mlproject_run.json")
    schema = read_json(root, "docs/openapi.json")
    spark = read_json(root, "reports/spark_etl.json")
    ray = read_json(root, "reports/ray_search.json")
    junit = ElementTree.parse(root / "reports/pytest.xml").getroot()
    suites = [junit] if junit.tag == "testsuite" else list(junit.findall("testsuite"))
    totals = {key: sum(int(s.get(key, "0")) for s in suites)
              for key in ("tests", "failures", "errors", "skipped")}
    passed = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    cases = junit.findall(".//testcase")
    if junit.tag == "testcase":
        cases = [junit]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=root, text=True).strip())
    day = final["evaluated_at"][:10]
    snapshot = f"Evidence snapshot: {day}. Source checkout: {commit[:12]}; uncommitted changes at generation: {dirty}."
    c = final["models"]["category"]
    p = final["models"]["priority"]
    review = final["review_policy"]
    metrics = table(
        ["Task", "Accuracy", "Macro-F1", "Majority macro-F1"],
        [(name.title(), f"{v['accuracy']:.4f}", f"{v['macro_f1']:.4f}", f"{v['majority_baseline_macro_f1']:.4f}")
         for name, v in final["models"].items()],
    )
    supports = table(["Task / class", "Test support", "Precision", "Recall", "F1"], [
        (f"{target} / {label}", count,
         f"{values['classification_report'][label]['precision']:.4f}",
         f"{values['classification_report'][label]['recall']:.4f}",
         f"{values['classification_report'][label]['f1-score']:.4f}")
        for target, values in final["models"].items()
        for label, count in values["class_support"].items()
    ])
    services = table(["Component", "Access", "Responsibility"], [
        ("React + Nginx", "127.0.0.1:3002", "Ticket UI; /api reverse proxy to FastAPI"),
        ("FastAPI", "127.0.0.1:8000", "Authentication, validation, routing, history, feedback, job API"),
        ("MLflow model server", "model:5001; private", "Original fitted pipelines plus explanation-enabled bundle"),
        ("Prometheus", "127.0.0.1:9090", "15-second scraping and availability rules"),
        ("Grafana", "127.0.0.1:3001", "Provisioned service, host and report panels"),
        ("Blackbox Exporter", "blackbox:9115; private", "HTTP probes of frontend, API, model and Grafana"),
        ("Node Exporter", "node-exporter:9100; private", "Host CPU, memory, root filesystem and load"),
        ("Report exporter", "reports-exporter:9108; private", "Existing CI, pipeline and drift summaries and age"),
        ("MLflow tracking", "127.0.0.1:5000; optional", "Experiments and artifacts; started separately when needed"),
        ("Terminal worker", "Authenticated HTTP client", "Runs fixed DVC stages in the AIops environment"),
    ])
    limits = """## Implemented scope and remaining limitations

This is a local educational demonstration using synthetic tickets. It suggests category, priority and routing; it does not repair incidents or create tickets in an external service.

- The 81-row test set is small. Class supports and per-class results accompany aggregate metrics. No confidence intervals or real-world generalization claims are provided.
- Scores are uncalibrated model preferences. The 0.60 review thresholds are demonstration policy, not calibrated risk guarantees. Most test tickets require review.
- The workflow uses TF-IDF, a majority baseline and balanced Logistic Regression. The blueprint's larger alternative-model and feature-ablation programme was simplified.
- The browser pipeline runs Spark ETL, training and evaluation of the frozen dataset. Acquisition, splitting, Ray tuning, feedback snapshots, feedback-candidate training and release switching are separate commands.
- Feedback retraining used one approved synthetic demonstration category correction. No genuine reviewed production cohort was available. Synthetic feedback was blocked by the promotion policy.
- Deployment and rollback were explicit stop/start exercises. Automatic quality-gated deployment and zero-downtime switching are not implemented.
- The worker runs in the host AIops environment, and MLflow Projects uses --env-manager local. A containerized training environment and fresh-machine environment parity were not demonstrated.
- A killed worker or prolonged API outage can leave a job active and locked. Automatic orphan recovery is not implemented; inspect processes and job state before recovery. Never clear an active-job guard while a child job could still be running.
- Drift checks run on demand. The last application report had 13 observations and insufficient_data. Report ages are visible; no scheduled persistent-drift retraining loop or labelled-cohort quality monitor is implemented.
- Host resource metrics and online service probes are implemented. Per-container resource metrics are not collected. MLflow tracking is manually checked when started; Spark and Ray stop between offline jobs.
- HTTP is restricted to local use. TLS, verified encrypted storage, automatic retention cleanup, rate limiting, prediction idempotency keys and a batch-prediction API are not implemented. A Docker volume is persistence, not encryption.
- The live pipeline UI and maintainer feedback review were manually exercised. Browser automation, exhaustive responsive/accessibility testing, security scanning and a sustained capacity benchmark have not been demonstrated.
- The KServe exercise deploys the model only, with one replica and port forwarding. The complete UI/API stack was not deployed to Kubernetes and autoscaling was disabled.
- Existing reports include an earlier nine-file DVC restore drill. A final fresh-checkout restore, image archive and tracking-store backup should be rehearsed at handover; these are procedures, not completed evidence in this snapshot.
"""
    files = {}
    files["architecture.md"] = f"""# AIOpsDesk - Architecture

DA3408 local AI application | As-built documentation

{snapshot}

## 1. Problem and boundary

AIOpsDesk assists an IT support operator by recommending one of four categories, one of two supported priority labels and a support team. The operator remains responsible for reviewing the recommendation. A viewer can submit a ticket, an operator can propose corrections, and a maintainer can review corrections and manage local pipeline jobs.

All compute and storage run on one local machine. The dataset was downloaded once from a pinned public revision. There is no paid inference API or cloud runtime dependency. Compose is the main application deployment; Kubernetes/KServe was a separate, stopped-after-use course exercise.

## 2. Architecture diagram

[[ARCHITECTURE_DIAGRAM]]

Solid arrows show the main prediction and persistence path. The terminal worker communicates with the API and executes offline commands in the repository. Prometheus observes the online services and exporters; it does not execute training or drift analysis.

## 3. Components and ports

{services}

## 4. Prediction path

1. A signed-in user enters a subject and opening description in the independent React UI.
2. Nginx forwards /api requests to FastAPI. The bearer token is held in browser memory.
3. FastAPI validates the input and calls the private MLflow /invocations endpoint, with a three-second model-call timeout.
4. The pyfunc bundle normalizes/redacts text, predicts category and priority, and computes bounded signed word/phrase contributions.
5. FastAPI validates model identity and scores, derives the support team from policy, and applies review thresholds.
6. The API stores the redacted input, original result, owner, timestamp, model version and policy version in SQLite before returning success.
7. History displays that saved result. A feedback review records a separate decision and does not rewrite the prediction.

## 5. Offline and control paths

Git versions code/configuration and small reports. DVC versions dataset directories, model artifacts and serving bundles, with a local remote outside the checkout. A grouped split manifest is reused by Spark-based training. Ray performed six bounded parameter trials and shut down. MLflow tracked experiments and packages; an MLproject entry point reproduced the DVC pipeline using the local environment.

The maintainer creates a job through the API. SQLite enforces one queued/running/cancel-requested job. A separate terminal worker claims it with a temporary secret and records ordered stage starts, finishes, counts and durations. Only fixed DVC commands are executed. Cancellation stops the subprocess group before the worker records a terminal result.

## 6. Storage and deployment isolation

- Current model: candidate-001; policy: policy-001; explanation capability bundle: explanations-001.
- Serving bundle: artifacts/serving/candidate-001-explained. Fitted classifier bytes are unchanged from candidate-001.
- Application database: /app/state/app/aiops.db in the external named volume aiopsdesk_app_data. The old host state/app database is a separate copy.
- Tracking metadata/artifacts: state/mlflow, managed by the optional host tracking server.
- API/model network: app_internal. Published loopback services also use app_access. The private model/exporters have no host-published ports.
- Prometheus/Grafana use named volumes; application/model containers have bounded resources and logs, nonroot users, and read-only root filesystems with explicit writable locations.

## 7. Evidence and interpretation

The HTTP/local-bundle comparison checked all 81 validation inputs. The KServe report checked the same number and recorded a Ready InferenceService. Container persistence, real pipeline execution, cache reuse, active cancellation/retry and model switch/rollback have separate saved reports.

Held-out results were calculated only after selection and review policy were frozen. Earlier test_set_used=false flags refer to their own earlier runs; the final test report correctly records test_set_used=true.

Primary evidence: docs/openapi.json; compose.yaml; dvc.yaml; reports/final_test_evaluation.json; reports/kserve_check.json; reports/release_switch_check.json; reports/pipeline_recovery_check.json.

For the full implementation boundary, see limitations.md. The source blueprint is a plan; this documentation describes the smaller implementation actually exercised.
"""
    routing = table(["Predicted category", "Policy team"], policy["category_to_team"].items())
    decisions = table(["Choice", "Reason and tradeoff"], [
        ("Small synthetic dataset", "Makes the lifecycle practical on one laptop; restricts realism and minority-class evidence."),
        ("TF-IDF + two Logistic Regression models", "Fast CPU inference, inspectable coefficients, independent targets; limited semantic understanding."),
        ("Grouped frozen splits", "Detected templates stay together; similarity detection is a safeguard rather than exhaustive paraphrase detection."),
        ("Balanced class weights", "Responds to measured class imbalance; raw scores remain uncalibrated."),
        ("Separate model/API/UI containers", "The UI consumes REST and imports no model code. Model serving remains usable with tracking stopped."),
        ("SQLite WAL + named volume", "Simple local persistence and transactions; one active training job and limited concurrent traffic."),
        ("Host terminal worker", "Reuses installed Python/Java/Spark/DVC and avoids a Docker socket in the app; needs its own terminal and recovery discipline."),
        ("JSON explanation column internally", "Keeps the MLflow tabular signature simple; FastAPI exposes a validated nested object."),
        ("Minimum 30 rows for drift", "Small demonstration support gate; insufficient_data is preserved for the 13-row application snapshot."),
        ("Separate KServe phase", "Demonstrates real InferenceService orchestration without running a second platform continuously."),
    ])
    files["hld.md"] = f"""# AIOpsDesk - High-Level Design

Design rationale, model decisions and measured outcome

{snapshot}

## 1. Goals and roles

Provide a nontechnical ticket form, auditable history, reviewed feedback, a visible bounded training pipeline and local monitoring. Viewer, operator and maintainer permissions are enforced by FastAPI, not just hidden navigation buttons. Support decisions remain human-controlled.

## 2. Dataset and split design

Source: {source['dataset']}. The source manifest records license {source['license']}, revision {source['revision']}, raw SHA-256 {source['sha256']} and retrieval time. There are {source['rows']} raw synthetic tickets, {prepared['retained_rows']} retained rows and {prepared['excluded_rows']} exclusions. Unsupported source labels are excluded with reasons rather than relabelled.

The retained classes are Software, Account, Network and Security; priorities are Medium and High. Subject and description are the model inputs. Source IDs, requester email, target columns and split metadata are not features.

Seed 42 produces 247 training, 81 validation and 81 test rows. Description token-set Jaccard similarity at 0.85 identified seven similar pairs and 405 groups; detected groups and ticket IDs do not cross splits. Stratification is approximate under group constraints. No chronology is inferred from this split.

## 3. Feature and model design

The fitted Pipeline is word TF-IDF (1-2 grams, max_features=5000, min_df=2) followed by balanced Logistic Regression. Category uses C=2.0 and priority C=0.5, max_iter=1000, random_state=42. Preprocessing is fitted only on training data. The serving wrapper applies deterministic whitespace and email normalization before invoking the fitted pipelines.

Ray compared C in 0.5, 1.0, 2.0 for each target: six trials, two allocated CPUs and one concurrent trial in the recorded search. Validation selected the parameters. The majority classifier supplies a simple comparison. The final serving bundle includes both fitted pipelines and their hash-checked metadata.

## 4. Policy and explanation

{routing}

Both category_score and priority_score must be at least 0.60 to avoid a low-score review warning. Scores are model preferences; they have not been calibrated. The application does not reset passwords or automatically assign an external ticket.

For each target, explanations compare the predicted class with its strongest alternative. Each contribution is a TF-IDF feature value multiplied by the relevant coefficient difference. Binary priority coefficients are handled separately. The intercept, displayed terms and omitted terms reconstruct the decision margin. Only five terms are displayed, with text stating which class each supports. An absent/invalid explanation does not discard a valid prediction.

## 5. Final test results

{metrics}

{supports}

Evaluation date: {final['evaluated_at']}. The test set has {final['test_rows']} rows. Log loss is {c['log_loss']:.4f} for category and {p['log_loss']:.4f} for priority; this is evaluation evidence, not proof of calibration.

{review['above_both_thresholds_rows']} rows ({100 * review['above_both_thresholds_fraction']:.1f}%) met both review thresholds; {review['requires_review_rows']} required review. In that selected 23-row subset, category accuracy was {c['accuracy_above_both_review_thresholds']:.4f} and priority accuracy {p['accuracy_above_both_review_thresholds']:.4f}. These conditional results must always be shown with subset size and coverage.

## 6. Lifecycle and release safeguards

The real browser pipeline executes Spark ETL, train and evaluate, or records reuse when DVC reports unchanged outputs. The fixed training dataset has 247 rows; pipeline validation has 81. Each job preserves its status, stage timing, counts, requester/reason and retry link. Quality rejection is distinct from process failure. No browser pipeline job deploys a model.

An approved synthetic feedback snapshot contained one reviewed category correction and no reviewed priority. A separate candidate trained category on 248 rows and copied priority unchanged. Category validation macro-F1 remained 0.7297. The promotion gate required operator_review labels and at least 0.001 macro-F1 improvement with no accuracy loss; this candidate was blocked. The separate exercise switched model and matching policy, verified images/health, and restored candidate-001/policy-001.

## 7. Resource and operations design

Spark runs local[2] with a 1 GB driver budget and exits. Ray stops after its bounded search. The KServe exercise used Minikube with two CPUs and 4096 MB in a separate phase; the cluster was stopped before Compose resumed. The main monitoring profile scrapes every 15 seconds. Report exporters describe saved measurements and expose their timestamps.

The short performance demonstration sent {perf['requests']} requests with concurrency {perf['concurrency']}: {perf['failed_requests']} failures, p50 {perf['p50_seconds'] * 1000:.2f} ms, p95 {perf['p95_seconds'] * 1000:.2f} ms and maximum {perf['maximum_seconds'] * 1000:.2f} ms. The measured window was {perf['wall_seconds']:.3f} seconds. Observed throughput of {perf['observed_requests_per_second']:.2f} requests/s applies only to this short run; it is not a sustained-capacity result.

## 8. Main design decisions

{decisions}

## 9. Deferred work

See limitations.md for the explicit gap list, including local-environment training, manual release actions, limited monitoring scope, optional tracking, no TLS/idempotency/batch API, and incomplete unattended recovery. These are documented simplifications rather than completed blueprint items.
"""
    operations = []
    for route, methods in schema["paths"].items():
        for method, operation in methods.items():
            if method not in {"get", "post", "delete", "put", "patch"}:
                continue
            body_schema = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            body_name = body_schema.get("$ref", "").split("/")[-1] or "None"
            protected = bool(operation.get("security", schema.get("security", [])))
            operations.append((method.upper(), route, body_name,
                               "Bearer" if protected else "Public",
                               ", ".join(operation.get("responses", {}))))
    operation_table = table(["Method", "Path", "Body schema", "Access", "Responses"], operations)
    db_rows = [
        ("predictions", "UUID, owner, redacted input/result JSON, model/policy versions and UTC creation time"),
        ("users / sessions", "Argon2 password hashes; hashed random bearer tokens with one-hour expiry"),
        ("feedback", "Prediction reference, independently reviewed category/priority, reason, author, source and status"),
        ("feedback_reviews", "One immutable decision per feedback ID, reviewer, reason and timestamp"),
        ("pipeline_runs", "Job ID/status, config version, reason, requester, retry link, timestamps, stages/summary JSON, worker claim hash and error code"),
    ]
    files["lld.md"] = f"""# AIOpsDesk - Low-Level Design

REST interfaces, data contracts and execution states

{snapshot}

## 1. Interface source of truth

The endpoint inventory below is generated from docs/openapi.json captured from the running API. Interactive documentation is at http://127.0.0.1:8000/docs. The public error body uses FastAPI's actual detail field (a message or validation-error list); the blueprint's proposed request_id/error envelope was not implemented.

The browser calls only its configurable API_BASE_URL, normally /api. Nginx strips that prefix and forwards requests to api:8000. The API makes private model calls to http://model:5001/invocations. The browser never loads classifier files.

## 2. Endpoint inventory

{operation_table}

Public endpoints cover health, safe model information and the local metrics scrape. Authenticated prediction/history are role-aware. Feedback submission is operator/maintainer; feedback review and all pipeline/worker routes are maintainer-only. Worker control additionally checks a temporary claim secret and the authenticated account.

## 3. Prediction contract

Example request, containing only creation-time text:

```json
{{
  "subject": "Cannot connect to office Wi-Fi",
  "description": "My laptop cannot connect. Other employees can connect normally."
}}
```

TicketInput forbids extra fields, strips outer whitespace, requires both strings and bounds their combined length to 5000 characters. Pydantic rejects missing/empty fields. The response contains prediction_id, result, model_version, policy_version, created_at and warnings. Result contains category, priority, finite scores in [0,1], team, needs_review, review_reasons and explanation.

The model's tabular response carries explanation_json internally. FastAPI parses a bounded object with available/unavailable status and category/priority explanations. Each available target contains predicted/alternative classes, up to five signed contributions, intercept, omitted-term sum, decision margin and a cautionary note. The parser verifies labels and margin reconstruction; a rejected explanation becomes unavailable independently of core inference.

## 4. Authentication, history and feedback

POST /v1/session returns a random bearer token; only its SHA-256 digest is stored. DELETE invalidates that session. Refreshing the UI clears its in-memory token and requires sign-in. Viewer history is owner-filtered; operators and maintainers may inspect all records. History uses descending SQLite rowid cursors and limit <=100. Cross-owner viewer lookup returns 404.

Feedback requires a prediction UUID, at least one supported corrected label, a reason and label_source. Unreviewed labels are omitted rather than copied from the model. Operator review is distinguished from synthetic_demo. A maintainer decision is approved or rejected; self-review is forbidden and a second decision returns conflict. Reviewed feedback does not update the original prediction.

## 5. Database entities and transactions

{table(['Entity', 'Stored information'], db_rows)}

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

{table(['Condition', 'Observed contract'], [
('Missing/invalid login', '401'), ('Insufficient role / worker claim mismatch', '403'),
('Unknown record or hidden viewer record', '404'), ('Active-job overlap or repeated review/invalid state transition', '409'),
('Invalid request schema', '422'), ('Model HTTP/response validation failure', '502'),
('Unavailable model/storage or failed readiness', '503'), ('Model transport timeout', '504'),
('Explanation invalid', 'Prediction retained with explanation unavailable'),
('Job process failure/timeout', 'Terminal error code and skipped downstream stages; serving model unchanged'),
])}

Unexpected process termination or prolonged API communication loss can retain an active job lock; no automatic stale-job reset is advertised. Worker errors are exposed as bounded codes; local logs provide diagnostics. Default Uvicorn access logs and pipeline logs are present; a complete structured request-correlation logging system is deferred.

## 9. Source map

src/api.py orchestrates prediction; auth.py and sessions.py implement identity; history.py, feedback.py and reviews.py implement audit workflows; snapshots.py exports approved labels; pipeline_jobs.py and pipeline_worker_api.py manage jobs; scripts/pipeline_worker.py executes them; linear_explanations.py and explanation_schema.py implement explainability. Frontend components consume these REST contracts. docs/openapi.json provides full schemas and required fields.
"""
    checktable = table(["ID", "Coverage", "Evidence / method"], [
        ("T01", "Schema, limits, extra fields", "pytest: invalid inputs and strict pipeline payloads"),
        ("T02", "Serving transform and output parity", "reports/model_http_check.json; explained_model_package.json"),
        ("T03", "Detected duplicate-group isolation", "reports/data_splits.json; final evaluation assertions"),
        ("T04", "Feature leakage exclusion", "Explicit subject/description-only input; training scripts"),
        ("T05", "Low-score review and routing", "pytest saved prediction test; policy.json"),
        ("T06", "Role/ownership controls", "pytest and session/history/feedback/review reports"),
        ("T07", "Immutable review and no self-review", "pytest; reports/review_check.json"),
        ("T08", "Explanation algebra and fallback", "Binary/multiclass fixtures; 162 validation explanations; API tests"),
        ("T09", "Single active job and worker ownership", "Concurrent create, claim identity and stage-order pytest cases"),
        ("T10", "Pipeline execute, reuse, cancel and retry", "evidence/pipeline-console; cancellation/recovery reports"),
        ("T11", "Local CI failure and recovery", "reports/ci_failure_demo.json and CI evidence"),
        ("T12", "DVC restore", "reports/restore_check.json: earlier nine-file drill"),
        ("T13", "Container persistence", "reports/container_check.json"),
        ("T14", "Drift controls and low support", "drift_validation, drift_synthetic_demo and drift_recent reports"),
        ("T15", "Promotion rejection and rollback", "promotion_decision.json; release_switch_check.json"),
        ("T16", "HTTP availability alert and recovery", "availability_alert_check.json"),
        ("T17", "Real KServe inference parity", "kserve_check.json: 81 validation inputs"),
        ("T18", "Short performance budget", "performance_check.json: 20 requests, concurrency 2"),
    ])
    cases_table = table(["Suite", "Executed pytest case"], [
        (case.get("classname", "").replace("tests.", ""), case.get("name", ""))
        for case in cases
    ])
    files["test-plan.md"] = f"""# AIOpsDesk - Test Plan and Results

Executed checks, case inventory and acceptance evidence

{snapshot}

## 1. Test strategy

Use temporary SQLite databases and disposable accounts for pytest. Model transport tests mock specific faults; live scripts separately exercise actual HTTP/model/container behaviour. Browser checks are manual. Keep the final test dataset outside parameter/threshold selection. Preserve actual outcomes and skipped/unsupported scope rather than assuming the entire planning checklist passed.

## 2. Automated test result

reports/pytest.xml records {totals['tests']} executed tests: {passed} passed, {totals['failures']} failed, {totals['errors']} errors and {totals['skipped']} skipped. Latest saved CI status is {ci['status']}, run {ci['run_id']}, with its own Git SHA and dirty flag. The anyio/pytest deprecation warning does not change the passing result.

```bash
python -m pytest tests -q --junitxml=reports/pytest.xml
python scripts/ci.py
```

CI runs compileall, pytest, DVC reproduction and the pipeline gate. Docker builds, browser checks and deployment are separate; the current ci.py does not automate the entire release chain.

## 3. Test cases and evidence map

{checktable}

## 4. Exact pytest case inventory

{cases_table}

## 5. Held-out model evaluation

{metrics}

{supports}

The frozen plan is reports/final_evaluation_plan.json. It records code, data/split, policy/settings and bundle-file hashes. reports/final_test_evaluation.json records the results. The evaluation used 81 test tickets, did not fit models or change deployment, and should not be repeated to choose different parameters.

The review policy selected 23 rows above both score thresholds and flagged 58 for review. Full-population scores remain the headline figures; selected-subset accuracy is conditional and has only 23 observations.

## 6. Performance acceptance and actual result

Declared budget before the run: zero invalid/failed responses and p95 <=1.0 second. Two independent HTTP clients submitted 20 marked synthetic demonstration tickets. Timing includes request, response parsing and client validation. Nearest-rank percentiles include all attempts.

{table(['Measurement', 'Observed value'], [
('Requests / concurrency', f"{perf['requests']} / {perf['concurrency']}"),
('Failed requests', perf['failed_requests']),
('p50 latency', f"{perf['p50_seconds'] * 1000:.2f} ms"),
('p95 latency', f"{perf['p95_seconds'] * 1000:.2f} ms"),
('Maximum latency', f"{perf['maximum_seconds'] * 1000:.2f} ms"),
('Measured wall time', f"{perf['wall_seconds']:.3f} seconds"),
('Short-run throughput', f"{perf['observed_requests_per_second']:.2f} requests/s"),
('Budget result', 'Passed' if perf['acceptance']['passed'] else 'Not met'),
])}

This very short run demonstrates responsiveness at the declared workload. It is not a stress, soak, saturation or maximum-throughput experiment. The report records actual running image IDs. PERFORMANCE DEMO records remain in history and must not be presented as independent natural traffic.

## 7. Manual workflows and monitoring

The user exercised prediction/history, operator feedback, maintainer rejection, the live pipeline screen, cache reuse, running cancellation and linked retry. Screenshots are supporting evidence only where actually captured. Skipped screenshots are not counted as completed artefacts. Browser automation and comprehensive viewport/keyboard audit were not run.

Monitoring verification reported the Node Exporter, report exporter and Grafana targets up, parsed pipeline/CI/drift reports successfully, and matched Node Exporter's host memory to /proc/meminfo. The saved states were pipeline=succeeded, CI=passed, drift=insufficient_data. An earlier frontend outage triggered an alert and cleared after recovery.

## 8. Release acceptance and outstanding work

Schema/authorization, immutable review, prediction persistence, numerical explanations, real pipeline execution, cancellation/retry, serving parity and explicit rollback have evidence. The feedback promotion decision remained keep_current_model. The explained bundle passed unchanged prediction/score parity.

Final handover should repeat startup and a fresh-checkout DVC restore after the final source commit. Automated browser tests, full fault/load/security coverage, TLS/encryption verification and unattended worker recovery remain outside the demonstrated scope. See limitations.md; an unexecuted test is not a pass.
"""
    files["user-manual.md"] = f"""# AIOpsDesk - User Manual

For viewers, support operators and local maintainers

Evidence date: {day}

## 1. What the application does

AIOpsDesk reads a ticket's subject and description and suggests a category, priority and support team. It is a learning demonstration. A person should confirm its recommendations. It cannot repair a network, reset an account or contact an external helpdesk.

Supported categories: Software, Account, Network and Security. Supported priorities: Medium and High. Do not enter passwords, access tokens or confidential customer information. Stored email strings are redacted, but this is not a general sensitive-data removal system.

## 2. Open and sign in

Open http://127.0.0.1:3002. Use your assigned local account and password. Viewer, operator and maintainer are roles with different permissions. Passwords are not included in this manual. The service badge should say ready. If it says unavailable, ask the maintainer to check the services before submitting.

Signing out invalidates the current session. Refreshing or closing the page clears its in-memory login; sign in again. An expired session also asks you to sign in.

## 3. Analyse a ticket

1. Choose Analyse.
2. Enter a short subject and an opening description. Both fields are required; together they may contain at most 5000 characters.
3. Click Analyse ticket once. Wait while the button is disabled.
4. Read the suggested category, priority and team. A Manual review required message means an operator should inspect it.
5. Expand Why did the model suggest this? to inspect influential words and phrases.
6. Open Prediction details for the saved identifier, model/policy versions and creation time.

Example subject: Cannot connect to office Wi-Fi. Description: My laptop cannot connect to the office Wi-Fi. Other employees can connect normally.

This example can predict Software rather than Network. That is a known limitation, not proof that the network is working. The explanation shows learned associations and which alternative class each term supports. A plus/minus contribution is a decision-score contribution, not a probability or a causal diagnosis. Other terms and model bias also contribute.

## 4. Read scores and review messages

Scores lie between zero and one. Higher means a stronger model preference. They have not been calibrated and should not be read as guaranteed accuracy. With policy-001, a category or priority score below 0.60 requires review. On the 81-ticket test set, 58 tickets required review. Even a high score can be wrong.

Explanations are shown for new predictions from the explanation-enabled bundle. Earlier saved records may say explanations unavailable. That does not change their original saved recommendation.

## 5. Inspect history

Choose History and select a ticket. View its redacted text, original result, scores, explanation when available, owner and versions. Refresh loads recent records; Load more retrieves the next page. A viewer sees only their own predictions. Operators and maintainers can inspect the shared demonstration history.

Records with PERFORMANCE DEMO subjects were created by the bounded performance check. They are artificial traffic and should be identified as such in analysis.

## 6. Submit feedback - operator or maintainer

1. Select a prediction in History.
2. Use its feedback form. Choose only category and/or priority labels you actually reviewed; leave the other target Not reviewed.
3. Enter a reason. Keep the practice-correction setting selected for a synthetic demonstration.
4. Inspect the confirmation preview, then save once.
5. Find the submission in Feedback. It starts Pending review.

A submitted correction does not rewrite the original prediction or immediately retrain a model. An unreviewed model label is not ground truth.

## 7. Review feedback - maintainer

Open Feedback and choose a pending submission from another account. Inspect the original ticket and proposed labels. Enter a decision reason, choose Approve or Reject, inspect the confirmation and confirm. The saved decision displays reviewer and time. A repeated decision is blocked, and you cannot review your own submission.

Approval makes a label eligible for an explicitly selected snapshot; it does not automatically replace a running model. Practice labels remain marked synthetic_demo.

## 8. Pipeline console - maintainer

The Pipeline screen displays the real Spark ETL -> Train -> Evaluate workflow. Acquisition, preparation, split IDs and selected model settings are already versioned inputs. The current console does not perform new feedback-candidate training or deployment.

An authorized terminal worker must be running. A maintainer starts it from the repository with the AIops environment active:

```bash
python -m scripts.pipeline_worker --once
```

Enter maintainer credentials privately. --once waits for and processes one job, then exits. Do not run separate manual training commands at the same time.

In the browser, enter a run reason. Leave Rebuild all stages unchecked to reuse unchanged results; select it for actual stage execution. Click Start pipeline. Only one queued, running or cancellation-requested job is allowed. A queued job waits until the worker is available.

Stage statuses mean Pending, Running, Succeeded, Reused, Failed, Cancelled, Interrupted or Skipped. Reused means the existing outputs were unchanged; it is not a fresh training run. Counts and elapsed seconds describe the recorded stage. The validation gate result is separate from deployment, and a successful job leaves the serving release unchanged.

To cancel, select the active job, enter a cancellation reason and confirm Request cancellation. A queued job cancels immediately. A running job first says Cancellation requested while the worker stops and cleans up. Wait for its final state before starting another job.

To retry a finished job, select it, click Prepare retry, review the reason/rebuild choice and start the retry. A new job ID links to the original. After an interrupted/cancelled job, a forced rebuild restores working pipeline outputs.

## 9. Monitoring

Grafana: http://127.0.0.1:3001/d/aiopsdesk-overview. Use the separate Grafana account; it is not the application maintainer account. Prometheus: http://127.0.0.1:9090.

Dashboards show API/model-call signals, host resources and saved report summaries. Scrapes occur every 15 seconds, so a change can take a scrape interval to appear. Report age shows how long ago CI, a pipeline job or a drift check ran. Scraping a report does not rerun its analysis. Insufficient data is an undetermined drift result, not a healthy/no-drift conclusion.

## 10. Troubleshooting

{table(['What you see', 'What to do'], [
('Service unavailable', 'Wait briefly and retry. Maintainer checks Compose status and model/API logs.'),
('Invalid or missing input', 'Read the field message; supply both text fields within 5000 combined characters.'),
('Prediction seems wrong', 'Inspect its explanation and ask an operator to submit reviewed feedback.'),
('History or Pipeline looks stale', 'Read the freshness time. Restore the connection; polling resumes while the tab is visible.'),
('Job stays queued', 'Start an authenticated terminal worker. Check that another job is not active.'),
('Cancellation requested persists', 'Inspect the worker terminal. Do not clear a database lock or start competing training blindly.'),
('Prometheus query has no data', 'Clear its fixed evaluation timestamp, execute again, and inspect targets.'),
('Frontend port already used', 'Stop the project Vite development server before publishing Docker port 3002; do not kill unrelated services.'),
])}

## 11. Maintainer startup and shutdown

From the initialized repository, with the existing local images and application database volume:

```bash
docker compose --profile observe up -d --wait --wait-timeout 180
docker compose --profile observe ps
curl --fail --silent --show-error http://127.0.0.1:3002/api/health/ready
```

Expected release: candidate-001 / policy-001. The model image includes the explanations-001 serving capability. MLflow tracking is optional and starts separately with bash scripts/start_mlflow.sh. It can remain stopped during ordinary predictions.

Stop the terminal worker with Ctrl+C when idle, then stop project services while retaining their storage:

```bash
docker compose --profile observe stop
```

Keep the Minikube profile stopped during normal Compose use. Avoid docker compose down -v: removing monitoring volumes loses their history; the application database is separately stored in an external named volume.

For fresh-checkout restoration, offline backups, account initialization and document rebuilding, see reproduction.md. For demo sequence and limitations, see demo-guide.md and limitations.md.
"""
    files["data-card.md"] = f"""# Dataset card

Source: {source['source_url']}

Publisher dataset ID: {source['dataset']}. Declared license recorded at acquisition: {source['license']}. Revision: {source['revision']}. Retrieved: {source['retrieved_at']}. Raw bytes: {source['bytes']}; raw rows: {source['rows']}; SHA-256: {source['sha256']}.

This is a synthetic IT-helpdesk dataset. The blueprint originally proposed a larger different source; the project deliberately selected this small dataset for learning and local resource limits. The source manifest is data/metadata/source.json. Preserve its license attribution when sharing the dataset; no new project-code license is inferred from the dataset license.

Preparation retained {prepared['retained_rows']} rows and excluded {prepared['excluded_rows']}: 88 unsupported-category records and 3 unsupported-priority records after category filtering. Original retained labels were preserved. The exclusion CSV and reports/data_preparation.json record this decision.

{table(['Category', 'Retained rows'], prepared['category_counts'].items())}

{table(['Priority', 'Retained rows'], prepared['priority_counts'].items())}

Model inputs are subject and description. Requester email, source ID/timestamps, labels and split metadata are not model features. Serving normalizes whitespace and redacts email strings. Metadata is preserved for provenance, not used to fabricate chronological evaluation.

Seed 42 grouped splitting retained 247/81/81 train/validation/test rows. Similarity grouping used description token-set Jaccard >=0.85; exact IDs and detected groups are disjoint. The source is small, imbalanced and synthetic, and the similarity detector cannot identify every semantic paraphrase. Account and Security test supports are only 14 and 9. Human-created demonstrations and load-check records are not independent test data.

Frozen test data was evaluated after parameter/policy selection; see final_test_evaluation.json. Approved feedback snapshots are separate from raw observations. The retraining demonstration used synthetic_demo labels and was blocked from quality promotion.
"""
    files["model-card.md"] = f"""# Model card - candidate-001

## Intended use

Local educational decision support for IT-ticket category, priority and policy routing. The operator confirms the recommendation. The system does not diagnose root cause or perform remediation.

## Model and lineage

Separate balanced Logistic Regression pipelines use word TF-IDF (1-2 grams, max_features=5000, min_df=2), seed 42, max_iter=1000. Selected C is 2.0 for category and 0.5 for priority. Six bounded Ray trials selected settings using validation macro-F1; Ray parent run {ray['parent_run_id']}. Training uses 247 rows; validation/test use 81 each. The input is subject + description, not true category or priority.

The current serving capability is explanations-001 at artifacts/serving/candidate-001-explained. It contains the original candidate-001 fitted bytes, records their hashes and adds signed text explanations. Model version and policy remain candidate-001 / policy-001. See explained_model_package.json and the final evaluation plan for content hashes.

## Final held-out results

{metrics}

{supports}

Category balanced accuracy {c['balanced_accuracy']:.4f}; priority balanced accuracy {p['balanced_accuracy']:.4f}. High-priority recall {p['classification_report']['High']['recall']:.4f}. Log loss {c['log_loss']:.4f} / {p['log_loss']:.4f}. Scores are not calibrated probabilities. Small synthetic class supports restrict interpretation.

The 0.60/0.60 review policy flags {review['requires_review_rows']} of 81 tickets. The selected above-threshold subset has 23 rows, category accuracy {c['accuracy_above_both_review_thresholds']:.4f} and priority accuracy {p['accuracy_above_both_review_thresholds']:.4f}; report this with its 28.4% coverage, never as whole-model accuracy.

## Explanations and known failure

Five signed TF-IDF contributions contrast the predicted class with the strongest alternative. They are associations in decision-score units. The intercept plus shown and omitted terms reconstruct the margin. Binary and multiclass numerical fixtures and 162 validation explanations were checked. The Wi-Fi example can predict Software rather than Network, with common terms influencing the result. An explanation makes that preference inspectable, not correct.

## Update and release policy

An approved synthetic category correction produced feedback-demo-001 trained on 248 category rows. Priority was copied unchanged. Validation macro-F1 did not improve. Promotion required operator_review feedback and >=0.001 improvement without accuracy regression; decision: {promotion['decision']}. The separate switch/rollback exercise tested operations, not evidence of model improvement. No automatic retraining or deployment is enabled.

## Limitations

Synthetic source, limited vocabulary/domain, class imbalance, small held-out sample, no formal calibration/uncertainty estimates, no real-world outcome cohort and no protected-attribute fairness study. A changed input distribution is not proof of concept drift. Do not tune against the frozen test results. See limitations.md for system-wide scope.
"""
    files["limitations.md"] = "# Scope, simplifications and remaining work\n\n" + limits + "\n## Maintenance priorities\n\n1. Rehearse fresh-checkout restore and package local images/tracking state.\n2. Add browser automation and explicit responsive/keyboard checks.\n3. Strengthen worker interruption recovery, input idempotency and structured audit logging.\n4. Add genuine reviewed cohorts, calibration/uncertainty evidence and a fixed promotion holdout before expanding release automation.\n5. Verify TLS, encryption and retention policy before handling sensitive records.\n"
    files["evidence-index.md"] = """# Evidence index

Reports describe their own measured run and code/data lineage. A report from an earlier component stage is historical evidence, not a claim that every later version was rerun with that exact script.

""" + table(["Area", "Evidence"], [
        ("Source and preparation", "data/metadata/source.json; reports/data_preparation.json"),
        ("Split isolation", "reports/data_splits.json; data/splits.dvc"),
        ("Baseline and tuning", "reports/baseline_metrics.json; reports/ray_search.json; reports/candidate_metrics.json"),
        ("Spark / DVC / Projects", "reports/spark_etl.json; dvc.yaml; dvc.lock; reports/mlproject_run.json"),
        ("Unit/integration tests and CI", "reports/pytest.xml; reports/ci_latest.json; evidence/ci"),
        ("CI failure / persistence", "reports/ci_failure_demo.json; reports/container_check.json"),
        ("Auth and review", "reports/session_check.json; history_check.json; feedback_check.json; review_check.json"),
        ("Real pipeline / cancellation / retry", "reports/pipeline_console_check.json; pipeline_cancellation_check.json; pipeline_recovery_check.json; evidence/pipeline-console"),
        ("Feedback and rejection", "reports/feedback_snapshot.json; feedback_training_check.json; feedback_candidate_metrics.json; promotion_decision.json"),
        ("Release exercise", "reports/release_switch_check.json; deploy/releases"),
        ("Explanations", "reports/explanation_validation.json; explained_model_package.json; explanation_http_check.json"),
        ("Monitoring", "reports/monitoring_coverage_check.json; availability_alert_check.json; monitoring/"),
        ("Drift", "reports/drift_validation.json; drift_synthetic_demo.json; drift_recent.json"),
        ("KServe", "reports/kserve_check.json; evidence/k8s; deploy/k8s"),
        ("Final evaluation", "reports/final_evaluation_plan.json; reports/final_test_evaluation.json"),
        ("Performance", "reports/performance_check.json"),
        ("Historical restore", "reports/restore_check.json"),
    ]) + "\n\nScreenshot filenames were suggested during the walkthrough, but this index does not assume that suggested or skipped screenshots exist in the repository. Add only files actually captured. The five PDF documents and their Markdown sources are listed by documentation-manifest.json.\n"
    files["demo-guide.md"] = f"""# Demo and viva guide

## Short demonstration

1. State the problem, local-only boundary and synthetic data limitation.
2. Open the UI, submit an ordinary ticket and an invalid/empty input. Show review status, versions and explanation. Use the known Wi-Fi misclassification to explain model limits.
3. Show owner-filtered history and an operator's pending practice correction. As maintainer, show a recorded decision and why self-review is forbidden.
4. Show a completed pipeline graph, actual counts/timing, a Reused run and the cancelled/retry pair. If running live, start the worker first; a cached run must be called reuse.
5. Open MLflow's recorded Ray/Projects runs when the tracking server is running. Explain that tracking and model serving are different processes.
6. Show Grafana service/host metrics and report age. Explain why drift_recent is insufficient_data and why the synthetic shift example is separate.
7. Show the promotion rejection and successful switch/rollback report; explain that the exercise did not establish better model quality.
8. Show final test metrics, the {totals['tests']}-test report, bounded performance results and the five documents. KServe has its own saved Ready/parity evidence and is normally stopped.

## Questions to prepare

- Why macro-F1 rather than only accuracy? Explain class imbalance and give class supports.
- Why two models? Priority does not receive the true category as a feature.
- How do Git, DVC and MLflow differ? Code/config, data/artifacts and experiment tracking respectively.
- Why Spark/Ray for a small dataset? Course-concept demonstrations with bounded compute; pandas would be simpler at this scale.
- What does confidence mean here? An uncalibrated model score, not a success probability.
- What is drift? A measured distribution change; reliable labels are needed to claim performance degradation or concept drift.
- What is immutable? Original predictions, review decisions and content-addressed snapshots; a retry creates a new job.
- What did cancellation prove? The worker acknowledged a running cancellation, skipped downstream stages and a linked retry succeeded without deploying.
- What does the load result prove? Only the short 20-request/two-client workload, not sustained capacity.
- Why keep Kubernetes separate? It demonstrates the controller/InferenceService contract while conserving laptop memory.
- Which proposed features remain unimplemented? Use limitations.md rather than claiming the whole blueprint is complete.

Assignments 1-10 revision questions were not supplied to this documentation build. Revise against the actual assignment sheets; do not claim this guide reproduces them.
"""
    files["reproduction.md"] = """# Reproduction and handover runbook

## Existing initialized checkout

Use the AIops environment from the project root. The existing external volume aiopsdesk_app_data contains the current accounts/history. Start the actual Compose configuration, not an old rollback override:

```bash
docker compose --profile observe up -d --wait --wait-timeout 180
docker compose --profile observe ps
curl --fail --silent --show-error http://127.0.0.1:3002/api/health/ready
```

Expected candidate-001 / policy-001. The model image is aiopsdesk-model:candidate-001-explained. Tracking is optional: bash scripts/start_mlflow.sh. Pipeline work requires python -m scripts.pipeline_worker --once in a separate terminal. Stop the worker before manual training/reproduction. Keep the Minikube aiopsdesk profile stopped during normal Compose operation.

## Fresh source and data restore

Complete a final source commit first. Clone that commit into a separate directory, configure the external local DVC remote using its real absolute path, and run dvc pull. Do not assume the machine-specific remote is committed. The walkthrough used a sibling aiopsdesk-dvc-store directory.

```bash
git clone --no-local /absolute/path/to/source /absolute/path/to/fresh-checkout
cd /absolute/path/to/fresh-checkout
dvc remote add --local -d local-store /absolute/path/to/aiopsdesk-dvc-store
dvc pull
dvc status
```

The absolute paths above are values to replace, not literal existing directories. Compare restored file hashes with the source checkout. The earlier restore_check.json covered nine baseline files; repeat with the final DVC-owned artifacts before claiming final-release recovery.

## Images and accounts

Compose sets pull_policy: never, so local image tags/digests must exist. Preserve an offline image archive for every Compose service, including the report-exporter alias; docker save and docker load operate on image archives. Monitoring images are pinned under deploy/docker. Build the API, explanation-model and frontend images with their recorded base digests if an archive is unavailable.

The application volume is external. Restore a consistent SQLite backup into it with restrictive ownership/permissions, or initialize an empty volume deliberately and create new local accounts. Never overwrite an existing application database as part of routine startup.

For a deliberately fresh installation, create the volume before Compose startup:

```bash
docker volume create aiopsdesk_app_data
```

After the API has initialized an empty database, create accounts interactively inside that container. Use this only when those usernames do not already exist:

```bash
docker compose exec api python -c '
from getpass import getpass
from src.auth import create_user
for role in ("viewer", "operator", "maintainer"):
    create_user(role, getpass(f"New {role} password: "), role)
'
```

Do not use the host create_users command to manage the container database: host state/app and the named-volume database are separate after migration. Keep private backups, sessions and credentials outside Git/DVC. Use SQLite's backup API rather than copying only a live .db file and omitting WAL state.

## Reproduce the offline pipeline

```bash
python scripts/ci.py
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
mlflow run . --env-manager local --experiment-name AIOpsDesk-project -P force=1
dvc push
```

The MLflow tracking server must be running for the Project command. Main DVC stages are Spark ETL, train and evaluate; acquisition, splitting and Ray selection are separate existing scripts/artifacts. The Project uses the activated local environment, not a training container. Do not rerun the final held-out evaluation to tune the model.

## Kubernetes exercise

Pause Compose and optional tracking before allocating Minikube memory. The recorded cluster used profile aiopsdesk, Docker driver, two CPUs, 4096 MB and Kubernetes v1.37.2. Prerequisites were cert-manager v1.21.3 and KServe v0.21.0. Create the kserve namespace before applying the KServe manifest; wait for CRDs to be Established and reapply before namespaced/custom resources if discovery races occur. Apply the committed Standard-mode patch, then the InferenceService manifest. Ingress creation and autoscaling are disabled.

The complete commands and pinned files are in deploy/k8s. Load aiopsdesk-model:candidate-001 into Minikube; this exercise deliberately tested the original serving image, not the later explanation-enabled image. Access the ready deployment with port forwarding to 15001:5001, then run scripts/check_kserve.py. The model speaks MLflow /invocations with dataframe_records; no native KServe V2 API is claimed. Stop port forwarding and minikube stop -p aiopsdesk before restoring Compose.

## Document rebuild

Keep documentation dependencies separate so requirements.txt and the DVC training dependency do not change:

```bash
python -m venv state/docs-venv
state/docs-venv/bin/python -m pip install -r docs/requirements-docs.txt
state/docs-venv/bin/python scripts/build_project_docs.py --repo . --out docs
```

The generator reads existing reports and OpenAPI, writes the five PDF documents and Markdown sources, updates README.md, and creates a source-hash manifest. It does not rerun tests, evaluate the test set, train, deploy or access passwords. Rebuilding regenerates the documentation sources; keep intentional editorial changes in Git before rerunning.

## Final rehearsal still to record

Perform one normal startup/health/login/prediction/stop cycle and a final clean-checkout DVC restore. Preserve image archives and a consistent tracking-store backup with the server stopped. Record actual completion and hashes; a written procedure alone is not evidence that the archive or drill succeeded.
"""
    readme = f"""# AIOpsDesk

Local educational IT-ticket triage with separate React/Nginx, FastAPI and MLflow serving containers. Inputs are subject and description; outputs are category, priority, policy team, review status and signed word/phrase explanations.

## Start the initialized deployment

```bash
docker compose --profile observe up -d --wait --wait-timeout 180
docker compose --profile observe ps
```

Open http://127.0.0.1:3002. API documentation: http://127.0.0.1:8000/docs. Grafana: http://127.0.0.1:3001. Prometheus: http://127.0.0.1:9090. Existing local images and the external aiopsdesk_app_data volume are required. Credentials are private and are not documented in source.

Current fitted model: candidate-001; policy: policy-001; explanation bundle: explanations-001. The model image is aiopsdesk-model:candidate-001-explained. Tracking on port 5000 is optional and starts with bash scripts/start_mlflow.sh. It is independent of inference.

## What is implemented

- Pinned 500-row synthetic source; 409 retained tickets; grouped 247/81/81 train/validation/test splits.
- Spark ETL, six bounded Ray trials, MLflow experiment tracking/serving/Projects, Git/DVC versioning and local CI.
- Three authenticated roles; ownership-filtered history; pending feedback and immutable maintainer review.
- Maintainer pipeline console with one-job guard, real stages/timings/counts, reuse, running cancellation and linked retry.
- Approved synthetic feedback retraining demonstration, quality rejection and explicit model/policy switch/rollback.
- Word-contribution explanations verified numerically and against 81 validation inputs.
- Prometheus/Grafana, HTTP probes/alert recovery, host metrics and timestamped report metrics.
- Separate local Minikube/KServe model exercise with HTTP parity evidence.

## Final measured results

{metrics}

The final test set has 81 synthetic tickets; 58 required review under the fixed 0.60 thresholds. Scores are not calibrated probabilities. {totals['tests']} pytest cases passed. The short 20-request, two-client performance check had zero failures and p95 {perf['p95_seconds'] * 1000:.2f} ms. This is a bounded demonstration, not a sustained-capacity claim.

## Main commands

```bash
python scripts/ci.py
python -m scripts.pipeline_worker --once
dvc status
dvc push
docker compose --profile observe stop
```

The worker runs in the activated AIops host environment. It processes browser-created jobs; keep it stopped during separate manual training. The main browser pipeline does not deploy models or automatically incorporate feedback. Do not rerun the locked test evaluation for tuning.

## Documentation

- [Architecture](docs/architecture.pdf) and [source](docs/architecture.md)
- [High-level design](docs/hld.pdf) and [source](docs/hld.md)
- [Low-level design](docs/lld.pdf) and [source](docs/lld.md)
- [Test plan and cases](docs/test-plan.pdf) and [source](docs/test-plan.md)
- [User manual](docs/user-manual.pdf) and [source](docs/user-manual.md)
- [Dataset card](docs/data-card.md), [model card](docs/model-card.md), [limitations](docs/limitations.md)
- [Reproduction/handover](docs/reproduction.md), [evidence index](docs/evidence-index.md), [demo/viva guide](docs/demo-guide.md)
- [REST schema](docs/openapi.json); docs/documentation-manifest.json links source-report hashes.

Dataset: {source['source_url']}; pinned revision and license metadata: data/metadata/source.json. Dataset substitution and scope reductions from the original blueprint are explicit in the documentation. A proposed feature is not marked implemented merely because it appears in the blueprint.
"""
    inputs = [
        "reports/final_test_evaluation.json", "reports/final_evaluation_plan.json",
        "reports/performance_check.json", "reports/pytest.xml", "reports/ci_latest.json",
        "reports/ray_search.json", "reports/spark_etl.json", "reports/kserve_check.json",
        "reports/monitoring_coverage_check.json", "reports/drift_recent.json",
        "reports/feedback_candidate_metrics.json", "reports/promotion_decision.json",
        "reports/mlproject_run.json", "reports/explained_model_package.json",
        "data/metadata/source.json", "reports/data_preparation.json", "reports/data_splits.json",
        "configs/policy.json", "configs/selected_models.json", "docs/openapi.json",
        "compose.yaml", "dvc.yaml", "dvc.lock",
    ]
    return files, readme, {
        "evidence_date": day, "source_git_sha": commit, "source_git_dirty": dirty,
        "test_counts": {**totals, "passed": passed},
        "source_hashes": {relative: digest(root / relative) for relative in inputs},
    }


NAVY = colors.HexColor("#17324d")
BLUE = colors.HexColor("#0072b2")
TEAL = colors.HexColor("#006b68")
PALE = colors.HexColor("#eef4fa")


class ArchitectureDiagram(Flowable):
    def __init__(self, width):
        super().__init__()
        self.width = width
        self.height = 215

    def draw(self):
        canvas = self.canv
        gap = 15
        box = (self.width - 2 * gap) / 3
        positions = [(0, 145), (box + gap, 145), (2 * (box + gap), 145),
                     (0, 45), (box + gap, 45), (2 * (box + gap), 45)]
        nodes = [
            ("Independent UI", "React + Nginx", "localhost:3002"),
            ("FastAPI", "Auth / policy / audit", "localhost:8000"),
            ("Model server", "MLflow pyfunc bundle", "private model:5001"),
            ("Terminal worker", "Spark -> train -> evaluate", "fixed DVC commands"),
            ("SQLite volume", "Predictions / feedback", "sessions / pipeline jobs"),
            ("Monitoring", "Prometheus + Grafana", "HTTP / host / reports"),
        ]
        for (x, y), lines in zip(positions, nodes):
            canvas.setFillColor(PALE)
            canvas.setStrokeColor(TEAL)
            canvas.roundRect(x, y, box, 57, 6, fill=1, stroke=1)
            for offset, line in enumerate(lines):
                canvas.setFillColor(NAVY)
                canvas.setFont("Helvetica-Bold" if offset == 0 else "Helvetica", 9 if offset == 0 else 8)
                canvas.drawCentredString(x + box / 2, y + 40 - offset * 14, line)

        def arrow(x1, y1, x2, y2):
            canvas.setStrokeColor(BLUE)
            canvas.setLineWidth(1.2)
            canvas.line(x1, y1, x2, y2)
            angle = math.atan2(y2 - y1, x2 - x1)
            for delta in (-0.55, 0.55):
                canvas.line(x2 - 5 * math.cos(angle + delta),
                            y2 - 5 * math.sin(angle + delta), x2, y2)

        arrow(box, 173, box + gap, 173)
        arrow(2 * box + gap, 173, 2 * (box + gap), 173)
        arrow(box + gap + box / 2, 145, box + gap + box / 2, 102)
        arrow(box, 75, box + gap, 155)
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(self.width / 2, 16, "Git + DVC version code/data/artifacts; optional MLflow tracking records experiments.")


def inline(text):
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def render_pdf(source, destination, title):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("DocBody", fontName="Helvetica", fontSize=9.5,
                              leading=12.8 if title == "User Manual" else 13.5,
                              textColor=NAVY, spaceAfter=6 if title == "User Manual" else 7))
    styles.add(ParagraphStyle("DocTitle", fontName="Helvetica-Bold", fontSize=23,
                              leading=28, textColor=NAVY, spaceAfter=16))
    styles.add(ParagraphStyle("DocHeading", fontName="Helvetica-Bold", fontSize=13,
                              leading=17, textColor=TEAL, spaceBefore=14,
                              spaceAfter=8))
    styles.add(ParagraphStyle("DocSubheading", fontName="Helvetica-Bold", fontSize=10.5,
                              leading=14, textColor=NAVY, spaceBefore=9,
                              spaceAfter=6))
    styles.add(ParagraphStyle("DocCell", fontName="Helvetica", fontSize=7.5,
                              leading=10.5, textColor=NAVY, wordWrap="CJK"))
    styles.add(ParagraphStyle("DocCode", fontName="Courier", fontSize=7.2,
                              leading=10, textColor=NAVY, backColor=PALE,
                              borderPadding=7, spaceBefore=5, spaceAfter=10))
    width = A4[0] - 32 * mm
    story = []
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("```"):
            block = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.extend(textwrap.wrap(lines[index], width=104,
                                           replace_whitespace=False,
                                           drop_whitespace=False) or [""])
                index += 1
            story.append(Preformatted("\n".join(block), styles["DocCode"]))
            index += 1
            continue
        if line == "[[ARCHITECTURE_DIAGRAM]]":
            story.append(ArchitectureDiagram(width))
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in row):
                    rows.append([Paragraph(inline(cell), styles["DocCell"]) for cell in row])
                index += 1
            n = len(rows[0])
            fractions = {2: [0.29, 0.71], 3: [0.24, 0.30, 0.46],
                         4: [0.34, 0.22, 0.22, 0.22],
                         5: [0.10, 0.34, 0.25, 0.13, 0.18]}.get(n, [1 / n] * n)
            # Metric tables benefit from a wider first column than API tables.
            if n == 5 and "Task / class" in line:
                fractions = [0.36, 0.16, 0.16, 0.16, 0.16]
            grid = LongTable(rows, colWidths=[width * f for f in fractions],
                             repeatRows=1, hAlign="LEFT")
            grid.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcebf5")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, BLUE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d3dce4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.extend([grid, Spacer(1, 8)])
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), styles["DocTitle"]))
            index += 1
            continue
        if line.startswith("## "):
            story.append(CondPageBreak(70))
            story.append(Paragraph(inline(line[3:]), styles["DocHeading"]))
            index += 1
            continue
        if line.startswith("### "):
            story.append(CondPageBreak(60))
            story.append(Paragraph(inline(line[4:]), styles["DocSubheading"]))
            index += 1
            continue
        if line.startswith("- "):
            story.append(Paragraph(inline(line[2:]), styles["DocBody"], bulletText="-"))
            index += 1
            continue
        if re.match(r"\d+\. ", line):
            story.append(Paragraph(inline(line), styles["DocBody"]))
            index += 1
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#|\||```|- |\d+\. )", lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        story.append(Paragraph(inline(" ".join(paragraph)), styles["DocBody"]))

    def chrome(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(TEAL)
        canvas.line(16 * mm, A4[1] - 13 * mm, A4[0] - 16 * mm, A4[1] - 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(NAVY)
        canvas.drawString(16 * mm, A4[1] - 10 * mm, "AIOpsDesk | DA3408 | As-built documentation")
        canvas.drawString(16 * mm, 10 * mm, title)
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(destination), pagesize=A4, leftMargin=16 * mm,
        rightMargin=16 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title=title, author="AIOpsDesk project", pageCompression=1,
    )
    document.build(story, onFirstPage=chrome, onLaterPages=chrome)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, default=Path("docs"))
    args = parser.parse_args()
    root = args.repo.resolve()
    out = args.out.resolve()
    files, readme, manifest = contents(root)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (out / name).write_text(text.strip() + "\n", encoding="utf-8")
    titles = {
        "architecture": "Architecture", "hld": "High-Level Design",
        "lld": "Low-Level Design", "test-plan": "Test Plan and Results",
        "user-manual": "User Manual",
    }
    for stem, title in titles.items():
        render_pdf(files[stem + ".md"], out / f"{stem}.pdf", title)
    (out.parent / "README.md").write_text(readme.strip() + "\n", encoding="utf-8")
    (out / "requirements-docs.txt").write_text("reportlab==4.4.9\n")
    manifest["generator_reportlab_version"] = reportlab_version
    manifest["generator_sha256"] = digest(Path(__file__).resolve())
    manifest["readme_sha256"] = digest(out.parent / "README.md")
    manifest["documents"] = {
        path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
        for path in sorted(out.iterdir())
        if path.is_file() and path.name != "documentation-manifest.json"
    }
    (out / "documentation-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print("DOCUMENTATION GENERATED")
    for stem in titles:
        print(out / f"{stem}.pdf")


if __name__ == "__main__":
    main()
