# Execution evidence

This directory keeps supplied screenshots and the execution records needed to demonstrate each distinct workflow. Screenshots are retained under their supplied names; suggested or skipped captures are not fabricated.

## Screenshots

`Screenshots/` contains the screenshots supplied by the project author. They have not been visually reviewed or modified as part of submission cleanup.

## Selected CI records

| Directory under `ci/` | Why it is retained |
| --- | --- |
| `20261111T065237918173Z/` | Deliberately failing test; the pipeline was blocked. |
| `20261111T065309980736Z/` | Successful recovery after the controlled failure. |
| `20261111T131644979567Z/` | Final recorded CI run with all 41 tests passing. |

Intermediate successful runs from earlier implementation stages were removed from the submission working tree. Their original versions remain in Git history. Failure/recovery reports and the final successful run remain available.

## Pipeline console records

| Job directory under `pipeline-console/` | Scenario |
| --- | --- |
| `2ec28630-16f4-4e1b-9ccd-d247c57463c5/` | First real API/worker execution. |
| `6e98b3e3-c5fd-4d7b-8e23-b73711e6f8b0/` | Browser-launched execution. |
| `0a9958d2-1fd3-40b1-a46d-421bf6abe1b9/` | Reused, unchanged DVC outputs. |
| `ef6347df-a9fc-480b-9bc9-70a91ad03dc0/` | Active cancellation during Spark ETL. |
| `507cfb23-9e8d-41d2-b729-16587cc35ea6/` | Linked retry and successful recovery. |

`k8s/` records the actual node, InferenceService and model workload state from the separate local KServe exercise. `mlproject/` records the real Projects/DVC execution log.

The JSON reports in `../reports/` explain results and lineage. Logs from different dates/commits are historical observations, not claims that every earlier check used the final version. See [the complete experiment report](../report.md) for the consolidated evidence and requirement mapping.
