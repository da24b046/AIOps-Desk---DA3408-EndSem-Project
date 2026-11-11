# AIOpsDesk

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

| Task | Accuracy | Macro-F1 | Majority macro-F1 |
| --- | --- | --- | --- |
| Category | 0.7778 | 0.7396 | 0.1811 |
| Priority | 0.8765 | 0.8742 | 0.3520 |

The final test set has 81 synthetic tickets; 58 required review under the fixed 0.60 thresholds. Scores are not calibrated probabilities. 41 pytest cases passed. The short 20-request, two-client performance check had zero failures and p95 25.25 ms. This is a bounded demonstration, not a sustained-capacity claim.

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

Dataset: https://huggingface.co/datasets/Console-AI/IT-helpdesk-synthetic-tickets; pinned revision and license metadata: data/metadata/source.json. Dataset substitution and scope reductions from the original blueprint are explicit in the documentation. A proposed feature is not marked implemented merely because it appears in the blueprint.
