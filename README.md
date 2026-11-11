# AIOpsDesk

A small local IT ticket classification application for learning and
demonstrating the AI application lifecycle.

## Current scope

- Inputs: ticket subject and description
- Category labels: Software, Account, Network, Security
- Priority labels: Medium, High
- Team routing: a configurable policy, to be implemented

## Dataset

Source: https://huggingface.co/datasets/Console-AI/IT-helpdesk-synthetic-tickets

The source contains 500 synthetic tickets.
Current preparation retains 409 tickets and excludes 91.
Original labels are preserved for retained tickets.

The pinned revision, download URL, license metadata and SHA-256 checksum
are recorded in data/metadata/source.json.

Synthetic-data results demonstrate the workflow; they do not establish
real-world IT support performance.

## Current commands

Run from the repository root with the project environment activated:

    python scripts/download_data.py
    python scripts/prepare_data.py

The download script refuses to overwrite an existing snapshot.
The preparation script regenerates its outputs from that snapshot.

## Data versioning

Raw and processed CSV files are ignored by Git.
DVC tracking and backup will be configured in a later step.
Until then, the local CSV files are not backed up by this Git commit.

## Current status

Implemented so far:
- Dataset preparation, grouped splits and baseline models.
- Spark ETL with output-parity verification.
- Ray parameter search and MLflow experiment tracking.
- DVC artifact storage and restore verification.
- Independent MLflow inference serving.
- FastAPI prediction, SQLite persistence and manual-review policy.
- Local login/logout, ownership-filtered history and reviewed feedback.

Separate API/model containers and persistent Compose deployment are implemented.
Frontend, lifecycle orchestration and monitoring remain under development.


## Local accounts and access

Create the three demo accounts interactively:

    python -m scripts.create_users

Passwords are entered privately and stored as Argon2 hashes.
Passwords and tokens must not be placed in the repository.

- Viewer: authenticated prediction and own prediction history.
- Operator: prediction review and feedback submission.
- Maintainer: feedback review and later lifecycle administration.

Feedback begins pending. Maintainers approve or reject it.
Self-review and repeated decisions are blocked.
Approval does not immediately retrain or replace a model.

Synthetic workflow feedback is marked synthetic_demo.

## Local services

Run each service in a separate terminal with the AIops environment active:

    bash scripts/start_mlflow.sh
    bash scripts/start_model_server.sh
    bash scripts/start_api.sh

- Tracking: http://127.0.0.1:5000
- Model inference: http://127.0.0.1:5001
- FastAPI documentation: http://127.0.0.1:8000/docs

Tracking may be stopped while the packaged inference service runs.
Application records and sessions are stored under state/app/.
Service state is ignored by Git.

The current API specification is saved in docs/openapi.json.


## Docker Compose deployment

Images:
- aiopsdesk-api:dev
- aiopsdesk-model:candidate-001

The application database uses the persistent external volume
aiopsdesk_app_data, initialized from a consistent local database backup.
Database backups and live state are excluded from Git and image builds.

Start the initialized deployment:

    docker compose up -d --wait --wait-timeout 120

Inspect services:

    docker compose ps

Stop and remove application containers while preserving database storage:

    docker compose down

API documentation: http://127.0.0.1:8000/docs

The model is reachable by the API at http://model:5001 on the internal
network. Its port is not published to the host.

The API also joins an access bridge network and publishes port 8000
only on host loopback.

Image identities are recorded in reports/docker_images.json.
Resolved runtime dependency snapshots are under deploy/docker/.
Container recreation and persistence were verified through the API.


## Containerized frontend

Frontend image: aiopsdesk-frontend:dev

Open http://127.0.0.1:3002 after starting Compose.
The frontend serves compiled React files using nonroot Nginx.
Requests under /api/ are forwarded to FastAPI.

The Compose deployment runs frontend, API and model independently.
Vite is used for development only and must be stopped before Docker
publishes frontend port 3002.

Node and Nginx base-image digests are recorded under deploy/docker/.
Frontend HTTP checks are recorded in reports/frontend_container_check.json.

Maintainer approval/rejection through the frontend remains pending
manual verification.
