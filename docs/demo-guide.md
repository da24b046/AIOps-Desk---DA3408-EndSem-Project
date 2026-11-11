# Demo and viva guide

## Short demonstration

1. State the problem, local-only boundary and synthetic data limitation.
2. Open the UI, submit an ordinary ticket and an invalid/empty input. Show review status, versions and explanation. Use the known Wi-Fi misclassification to explain model limits.
3. Show owner-filtered history and an operator's pending practice correction. As maintainer, show a recorded decision and why self-review is forbidden.
4. Show a completed pipeline graph, actual counts/timing, a Reused run and the cancelled/retry pair. If running live, start the worker first; a cached run must be called reuse.
5. Open MLflow's recorded Ray/Projects runs when the tracking server is running. Explain that tracking and model serving are different processes.
6. Show Grafana service/host metrics and report age. Explain why drift_recent is insufficient_data and why the synthetic shift example is separate.
7. Show the promotion rejection and successful switch/rollback report; explain that the exercise did not establish better model quality.
8. Show final test metrics, the 41-test report, bounded performance results and the five documents. KServe has its own saved Ready/parity evidence and is normally stopped.

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
