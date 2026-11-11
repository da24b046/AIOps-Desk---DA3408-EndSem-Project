# Scope, simplifications and remaining work

## Implemented scope and remaining limitations

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

## Maintenance priorities

1. Rehearse fresh-checkout restore and package local images/tracking state.
2. Add browser automation and explicit responsive/keyboard checks.
3. Strengthen worker interruption recovery, input idempotency and structured audit logging.
4. Add genuine reviewed cohorts, calibration/uncertainty evidence and a fixed promotion holdout before expanding release automation.
5. Verify TLS, encryption and retention policy before handling sensitive records.
