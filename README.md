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

Dataset acquisition and initial preparation are complete.
Models, services and deployment have not been implemented.
