# AIOpsDesk - Test Plan and Results

Executed checks, case inventory and acceptance evidence

Evidence snapshot: 2026-11-11. Source checkout: 280ba66edbba; uncommitted changes at generation: True.

## 1. Test strategy

Use temporary SQLite databases and disposable accounts for pytest. Model transport tests mock specific faults; live scripts separately exercise actual HTTP/model/container behaviour. Browser checks are manual. Keep the final test dataset outside parameter/threshold selection. Preserve actual outcomes and skipped/unsupported scope rather than assuming the entire planning checklist passed.

## 2. Automated test result

reports/pytest.xml records 41 executed tests: 41 passed, 0 failed, 0 errors and 0 skipped. Latest saved CI status is passed, run 20261111T131644979567Z, with its own Git SHA and dirty flag. The anyio/pytest deprecation warning does not change the passing result.

```bash
python -m pytest tests -q --junitxml=reports/pytest.xml
python scripts/ci.py
```

CI runs compileall, pytest, DVC reproduction and the pipeline gate. Docker builds, browser checks and deployment are separate; the current ci.py does not automate the entire release chain.

## 3. Test cases and evidence map

| ID | Coverage | Evidence / method |
| --- | --- | --- |
| T01 | Schema, limits, extra fields | pytest: invalid inputs and strict pipeline payloads |
| T02 | Serving transform and output parity | reports/model_http_check.json; explained_model_package.json |
| T03 | Detected duplicate-group isolation | reports/data_splits.json; final evaluation assertions |
| T04 | Feature leakage exclusion | Explicit subject/description-only input; training scripts |
| T05 | Low-score review and routing | pytest saved prediction test; policy.json |
| T06 | Role/ownership controls | pytest and session/history/feedback/review reports |
| T07 | Immutable review and no self-review | pytest; reports/review_check.json |
| T08 | Explanation algebra and fallback | Binary/multiclass fixtures; 162 validation explanations; API tests |
| T09 | Single active job and worker ownership | Concurrent create, claim identity and stage-order pytest cases |
| T10 | Pipeline execute, reuse, cancel and retry | evidence/pipeline-console; cancellation/recovery reports |
| T11 | Local CI failure and recovery | reports/ci_failure_demo.json and CI evidence |
| T12 | DVC restore | reports/restore_check.json: earlier nine-file drill |
| T13 | Container persistence | reports/container_check.json |
| T14 | Drift controls and low support | drift_validation, drift_synthetic_demo and drift_recent reports |
| T15 | Promotion rejection and rollback | promotion_decision.json; release_switch_check.json |
| T16 | HTTP availability alert and recovery | availability_alert_check.json |
| T17 | Real KServe inference parity | kserve_check.json: 81 validation inputs |
| T18 | Short performance budget | performance_check.json: 20 requests, concurrency 2 |

## 4. Exact pytest case inventory

| Suite | Executed pytest case |
| --- | --- |
| test_api | test_anonymous_prediction_rejected |
| test_api | test_prediction_persisted_redacted_and_flagged |
| test_api | test_invalid_input_creates_no_prediction[payload0] |
| test_api | test_invalid_input_creates_no_prediction[payload1] |
| test_api | test_invalid_input_creates_no_prediction[payload2] |
| test_api | test_invalid_input_creates_no_prediction[payload3] |
| test_api | test_feedback_review_permissions_and_single_decision |
| test_api | test_self_review_forbidden |
| test_api | test_viewer_cannot_read_another_users_prediction |
| test_api | test_model_timeout_translated_to_504 |
| test_api | test_wrong_model_version_rejected |
| test_api | test_failed_database_write_does_not_return_success |
| test_api | test_metrics_exclude_ticket_text_and_identifiers |
| test_api | test_legacy_model_without_explanation_still_predicts |
| test_api | test_valid_explanation_is_returned_and_saved |
| test_api | test_invalid_explanation_does_not_discard_valid_prediction[invalid_json] |
| test_api | test_invalid_explanation_does_not_discard_valid_prediction[wrong_class] |
| test_linear_explanations | test_binary_contributions_have_correct_sign_and_margin[alpha-Medium-2.25] |
| test_linear_explanations | test_binary_contributions_have_correct_sign_and_margin[beta-High-0.75] |
| test_linear_explanations | test_binary_contributions_have_correct_sign_and_margin[alpha beta-Medium-1.25] |
| test_linear_explanations | test_unfamiliar_text_reports_intercept_only |
| test_linear_explanations | test_multiclass_contrast_and_omitted_terms |
| test_pipeline_jobs | test_anonymous_job_access_rejected |
| test_pipeline_jobs | test_non_maintainer_job_access_forbidden[viewer] |
| test_pipeline_jobs | test_non_maintainer_job_access_forbidden[operator] |
| test_pipeline_jobs | test_concurrent_requests_allow_only_one_job |
| test_pipeline_jobs | test_queued_cancel_and_retry_preserve_history |
| test_pipeline_jobs | test_unsafe_or_invalid_job_fields_rejected[payload0] |
| test_pipeline_jobs | test_unsafe_or_invalid_job_fields_rejected[payload1] |
| test_pipeline_jobs | test_unsafe_or_invalid_job_fields_rejected[payload2] |
| test_pipeline_jobs | test_unsafe_or_invalid_job_fields_rejected[payload3] |
| test_pipeline_jobs | test_running_cancel_keeps_single_job_guard |
| test_pipeline_jobs | test_unknown_job_and_retry_return_404 |
| test_pipeline_jobs | test_worker_claim_is_exclusive_and_secret_is_hidden |
| test_pipeline_jobs | test_non_maintainer_cannot_claim_jobs[viewer] |
| test_pipeline_jobs | test_non_maintainer_cannot_claim_jobs[operator] |
| test_pipeline_jobs | test_anonymous_worker_claim_rejected |
| test_pipeline_jobs | test_ordered_stages_and_success_gate |
| test_pipeline_jobs | test_worker_acknowledges_cancellation_before_guard_releases |
| test_pipeline_jobs | test_failed_stage_prevents_later_execution |
| test_pipeline_jobs | test_worker_claim_is_bound_to_authenticated_account |

## 5. Held-out model evaluation

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

The frozen plan is reports/final_evaluation_plan.json. It records code, data/split, policy/settings and bundle-file hashes. reports/final_test_evaluation.json records the results. The evaluation used 81 test tickets, did not fit models or change deployment, and should not be repeated to choose different parameters.

The review policy selected 23 rows above both score thresholds and flagged 58 for review. Full-population scores remain the headline figures; selected-subset accuracy is conditional and has only 23 observations.

## 6. Performance acceptance and actual result

Declared budget before the run: zero invalid/failed responses and p95 <=1.0 second. Two independent HTTP clients submitted 20 marked synthetic demonstration tickets. Timing includes request, response parsing and client validation. Nearest-rank percentiles include all attempts.

| Measurement | Observed value |
| --- | --- |
| Requests / concurrency | 20 / 2 |
| Failed requests | 0 |
| p50 latency | 18.36 ms |
| p95 latency | 25.25 ms |
| Maximum latency | 28.99 ms |
| Measured wall time | 0.203 seconds |
| Short-run throughput | 98.58 requests/s |
| Budget result | Passed |

This very short run demonstrates responsiveness at the declared workload. It is not a stress, soak, saturation or maximum-throughput experiment. The report records actual running image IDs. PERFORMANCE DEMO records remain in history and must not be presented as independent natural traffic.

## 7. Manual workflows and monitoring

The user exercised prediction/history, operator feedback, maintainer rejection, the live pipeline screen, cache reuse, running cancellation and linked retry. Screenshots are supporting evidence only where actually captured. Skipped screenshots are not counted as completed artefacts. Browser automation and comprehensive viewport/keyboard audit were not run.

Monitoring verification reported the Node Exporter, report exporter and Grafana targets up, parsed pipeline/CI/drift reports successfully, and matched Node Exporter's host memory to /proc/meminfo. The saved states were pipeline=succeeded, CI=passed, drift=insufficient_data. An earlier frontend outage triggered an alert and cleared after recovery.

## 8. Release acceptance and outstanding work

Schema/authorization, immutable review, prediction persistence, numerical explanations, real pipeline execution, cancellation/retry, serving parity and explicit rollback have evidence. The feedback promotion decision remained keep_current_model. The explained bundle passed unchanged prediction/score parity.

Final handover should repeat startup and a fresh-checkout DVC restore after the final source commit. Automated browser tests, full fault/load/security coverage, TLS/encryption verification and unattended worker recovery remain outside the demonstrated scope. See limitations.md; an unexecuted test is not a pass.
