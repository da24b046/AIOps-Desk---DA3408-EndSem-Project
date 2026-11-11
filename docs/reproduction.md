# Reproduction and handover runbook

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
