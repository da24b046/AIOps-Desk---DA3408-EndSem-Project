# AIOpsDesk - High-Level Design

Design rationale, model decisions and measured outcome

Reviewed for submission using the recorded 2026-11-11 measurements and completed handover checks. Evidence paths and scope are consolidated in the root report.md; document hashes are recorded in reports/documentation_check.json.

## 1. Goals and roles

Provide a nontechnical ticket form, auditable history, reviewed feedback, a visible bounded training pipeline and local monitoring. Viewer, operator and maintainer permissions are enforced by FastAPI, not just hidden navigation buttons. Support decisions remain human-controlled.

## 2. Dataset and split design

Source: Console-AI/IT-helpdesk-synthetic-tickets. The source manifest records license mit, revision 165693849d955c6da4c00bc8be8e541afec0514e, raw SHA-256 27ffa4446d557278a8e1922b8f639fb9d104c13676c18927793e52e3f45c0151 and retrieval time. There are 500 raw synthetic tickets, 409 retained rows and 91 exclusions. Unsupported source labels are excluded with reasons rather than relabelled.

The retained classes are Software, Account, Network and Security; priorities are Medium and High. Subject and description are the model inputs. Source IDs, requester email, target columns and split metadata are not features.

Seed 42 produces 247 training, 81 validation and 81 test rows. Description token-set Jaccard similarity at 0.85 identified seven similar pairs and 405 groups; detected groups and ticket IDs do not cross splits. Stratification is approximate under group constraints. No chronology is inferred from this split.

## 3. Feature and model design

The fitted Pipeline is word TF-IDF (1-2 grams, max_features=5000, min_df=2) followed by balanced Logistic Regression. Category uses C=2.0 and priority C=0.5, max_iter=1000, random_state=42. Preprocessing is fitted only on training data. The serving wrapper applies deterministic whitespace and email normalization before invoking the fitted pipelines.

Ray compared C in 0.5, 1.0, 2.0 for each target: six trials, two allocated CPUs and one concurrent trial in the recorded search. Validation selected the parameters. The majority classifier supplies a simple comparison. The final serving bundle includes both fitted pipelines and their hash-checked metadata.

## 4. Policy and explanation

| Predicted category | Policy team |
| --- | --- |
| Software | Application Support |
| Account | Identity Support |
| Network | Network Support |
| Security | Security Support |

Both category_score and priority_score must be at least 0.60 to avoid a low-score review warning. Scores are model preferences; they have not been calibrated. The application does not reset passwords or automatically assign an external ticket.

For each target, explanations compare the predicted class with its strongest alternative. Each contribution is a TF-IDF feature value multiplied by the relevant coefficient difference. Binary priority coefficients are handled separately. The intercept, displayed terms and omitted terms reconstruct the decision margin. Only five terms are displayed, with text stating which class each supports. An absent/invalid explanation does not discard a valid prediction.

## 5. Final test results

| Task | Accuracy | Macro-F1 | Majority macro-F1 |
| --- | --- | --- | --- |
| Category | 0.7778 | 0.7396 | 0.1811 |
| Priority | 0.8765 | 0.8742 | 0.3520 |

| Task / class | Test support | Precision | Recall | F1 |
| --- | --- | --- | --- | --- |
| category / Account | 14 | 0.6154 | 0.5714 | 0.5926 |
| category / Network | 12 | 0.8182 | 0.7500 | 0.7826 |
| category / Security | 9 | 0.8571 | 0.6667 | 0.7500 |
| category / Software | 46 | 0.8000 | 0.8696 | 0.8333 |
| priority / High | 37 | 0.9091 | 0.8108 | 0.8571 |
| priority / Medium | 44 | 0.8542 | 0.9318 | 0.8913 |

Evaluation date: 2026-11-11T13:29:41.147694+00:00. The test set has 81 rows. Log loss is 0.6838 for category and 0.4892 for priority; this is evaluation evidence, not proof of calibration.

23 rows (28.4%) met both review thresholds; 58 required review. In that selected 23-row subset, category accuracy was 1.0000 and priority accuracy 0.8261. These conditional results must always be shown with subset size and coverage.

## 6. Lifecycle and release safeguards

The real browser pipeline executes Spark ETL, train and evaluate, or records reuse when DVC reports unchanged outputs. The fixed training dataset has 247 rows; pipeline validation has 81. Each job preserves its status, stage timing, counts, requester/reason and retry link. Quality rejection is distinct from process failure. No browser pipeline job deploys a model.

An approved synthetic feedback snapshot contained one reviewed category correction and no reviewed priority. A separate candidate trained category on 248 rows and copied priority unchanged. Category validation macro-F1 remained 0.7297. The promotion gate required operator_review labels and at least 0.001 macro-F1 improvement with no accuracy loss; this candidate was blocked. The separate exercise switched model and matching policy, verified images/health, and restored candidate-001/policy-001.

## 7. Resource and operations design

Spark runs local[2] with a 1 GB driver budget and exits. Ray stops after its bounded search. The KServe exercise used Minikube with two CPUs and 4096 MB in a separate phase; the cluster was stopped before Compose resumed. The main monitoring profile scrapes every 15 seconds. Report exporters describe saved measurements and expose their timestamps.

The short performance demonstration sent 20 requests with concurrency 2: 0 failures, p50 18.36 ms, p95 25.25 ms and maximum 28.99 ms. The measured window was 0.203 seconds. Observed throughput of 98.58 requests/s applies only to this short run; it is not a sustained-capacity result.

## 8. Main design decisions

| Choice | Reason and tradeoff |
| --- | --- |
| Small synthetic dataset | Makes the lifecycle practical on one laptop; restricts realism and minority-class evidence. |
| TF-IDF + two Logistic Regression models | Fast CPU inference, inspectable coefficients, independent targets; limited semantic understanding. |
| Grouped frozen splits | Detected templates stay together; similarity detection is a safeguard rather than exhaustive paraphrase detection. |
| Balanced class weights | Responds to measured class imbalance; raw scores remain uncalibrated. |
| Separate model/API/UI containers | The UI consumes REST and imports no model code. Model serving remains usable with tracking stopped. |
| SQLite WAL + named volume | Simple local persistence and transactions; one active training job and limited concurrent traffic. |
| Host terminal worker | Reuses installed Python/Java/Spark/DVC and avoids a Docker socket in the app; needs its own terminal and recovery discipline. |
| JSON explanation column internally | Keeps the MLflow tabular signature simple; FastAPI exposes a validated nested object. |
| Minimum 30 rows for drift | Small demonstration support gate; insufficient_data is preserved for the 13-row application snapshot. |
| Separate KServe phase | Demonstrates real InferenceService orchestration without running a second platform continuously. |

## 9. Deferred work

See the root report.md, section 12, for the explicit gap list, including local-environment training, manual release actions, limited monitoring scope, optional tracking, no TLS/idempotency/batch API, and incomplete unattended recovery. These are documented simplifications rather than completed blueprint items.
