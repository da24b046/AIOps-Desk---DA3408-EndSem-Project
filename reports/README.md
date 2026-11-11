# Measured results and verification reports

Small machine-readable reports belong in Git. Large data/model binaries belong in DVC, and live databases/session state stay outside Git.

## Start here

| Report | Meaning |
| --- | --- |
| `final_evaluation_plan.json` | Frozen data, policy, settings and serving-bundle hashes before final test evaluation. |
| `final_test_evaluation.json` | Final 81-ticket held-out results, class supports and review-policy coverage. |
| `performance_check.json` | 20-request, concurrency-2 workload with per-request measurements. |
| `ci_latest.json`, `pytest.xml` | Final recorded CI outcome and 41 executed pytest cases. |
| `final_restore_check.json` | Fresh checkout restored all 53 DVC-owned files with matching hashes. |
| `final_startup_check.json` | Eight services, preserved account/history, ten scrape targets and four probes after restart. |
| `docker_images.json` | Runtime image references/IDs from the final startup record and current build-configuration hashes. |
| `documentation_check.json` | Current six-PDF layout and source-document hashes. |
| `submission_tests.xml` | Fresh 41-test pass against disposable databases during final preparation. |
| `submission_check.json` | Folder-by-folder Git audit, including a fresh source-only restore using the included DVC backup. |

## Supporting evidence

- **Data/model development:** `data_preparation`, `data_splits`, `baseline_metrics`, `ray_search`, `candidate_metrics`, `spark_etl`, `pipeline_evaluation`.
- **Serving/explanations:** `model_package`, `model_http_check`, `serving_independence`, `explained_model_package`, `explanation_validation`, `explanation_http_check`.
- **Application workflows:** `session_check`, `history_check`, `feedback_check`, `review_check`, `container_check`.
- **Lifecycle:** `pipeline_console_check`, `pipeline_cancellation_check`, `pipeline_recovery_check`, `feedback_training_check`, `feedback_candidate_metrics`, `promotion_decision`, `release_switch_check`.
- **Monitoring/drift:** `monitoring_coverage_check`, `availability_alert_check`, `component_probe_check`, `drift_validation`, `drift_synthetic_demo`, `drift_recent`.
- **Course-topic exercises:** `mlproject_run`, `kserve_check`.

Names above are JSON files unless another extension is shown. Other small reports preserve source/package metadata or earlier component checks referenced by the code and documentation; they are retained for reproducibility.

`*_latest` files summarize the last saved run. Their timestamps matter. Scraping them does not execute another CI/pipeline/drift check. A historical `test_set_used: false` describes that particular earlier run; the final held-out report correctly records `true`.

The current drift report has insufficient data. Synthetic shift demonstrations, reviewed practice feedback and PERFORMANCE DEMO traffic are not natural production observations. No additional test-set tuning was performed during submission preparation.
