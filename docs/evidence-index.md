# Evidence index

Reports describe their own measured run and code/data lineage. A report from an earlier component stage is historical evidence, not a claim that every later version was rerun with that exact script.

| Area | Evidence |
| --- | --- |
| Source and preparation | data/metadata/source.json; reports/data_preparation.json |
| Split isolation | reports/data_splits.json; data/splits.dvc |
| Baseline and tuning | reports/baseline_metrics.json; reports/ray_search.json; reports/candidate_metrics.json |
| Spark / DVC / Projects | reports/spark_etl.json; dvc.yaml; dvc.lock; reports/mlproject_run.json |
| Unit/integration tests and CI | reports/pytest.xml; reports/ci_latest.json; evidence/ci |
| CI failure / persistence | reports/ci_failure_demo.json; reports/container_check.json |
| Auth and review | reports/session_check.json; history_check.json; feedback_check.json; review_check.json |
| Real pipeline / cancellation / retry | reports/pipeline_console_check.json; pipeline_cancellation_check.json; pipeline_recovery_check.json; evidence/pipeline-console |
| Feedback and rejection | reports/feedback_snapshot.json; feedback_training_check.json; feedback_candidate_metrics.json; promotion_decision.json |
| Release exercise | reports/release_switch_check.json; deploy/releases |
| Explanations | reports/explanation_validation.json; explained_model_package.json; explanation_http_check.json |
| Monitoring | reports/monitoring_coverage_check.json; availability_alert_check.json; monitoring/ |
| Drift | reports/drift_validation.json; drift_synthetic_demo.json; drift_recent.json |
| KServe | reports/kserve_check.json; evidence/k8s; deploy/k8s |
| Final evaluation | reports/final_evaluation_plan.json; reports/final_test_evaluation.json |
| Performance | reports/performance_check.json |
| Historical restore | reports/restore_check.json |

Screenshot filenames were suggested during the walkthrough, but this index does not assume that suggested or skipped screenshots exist in the repository. Add only files actually captured. The five PDF documents and their Markdown sources are listed by documentation-manifest.json.
