# AIOpsDesk - User Manual

For viewers, support operators and local maintainers

Evidence date: 2026-11-11

## 1. What the application does

AIOpsDesk reads a ticket's subject and description and suggests a category, priority and support team. It is a learning demonstration. A person should confirm its recommendations. It cannot repair a network, reset an account or contact an external helpdesk.

Supported categories: Software, Account, Network and Security. Supported priorities: Medium and High. Do not enter passwords, access tokens or confidential customer information. Stored email strings are redacted, but this is not a general sensitive-data removal system.

## 2. Open and sign in

Open http://127.0.0.1:3002. Use your assigned local account and password. Viewer, operator and maintainer are roles with different permissions. Passwords are not included in this manual. The service badge should say ready. If it says unavailable, ask the maintainer to check the services before submitting.

Signing out invalidates the current session. Refreshing or closing the page clears its in-memory login; sign in again. An expired session also asks you to sign in.

## 3. Analyse a ticket

1. Choose Analyse.
2. Enter a short subject and an opening description. Both fields are required; together they may contain at most 5000 characters.
3. Click Analyse ticket once. Wait while the button is disabled.
4. Read the suggested category, priority and team. A Manual review required message means an operator should inspect it.
5. Expand Why did the model suggest this? to inspect influential words and phrases.
6. Open Prediction details for the saved identifier, model/policy versions and creation time.

Example subject: Cannot connect to office Wi-Fi. Description: My laptop cannot connect to the office Wi-Fi. Other employees can connect normally.

This example can predict Software rather than Network. That is a known limitation, not proof that the network is working. The explanation shows learned associations and which alternative class each term supports. A plus/minus contribution is a decision-score contribution, not a probability or a causal diagnosis. Other terms and model bias also contribute.

## 4. Read scores and review messages

Scores lie between zero and one. Higher means a stronger model preference. They have not been calibrated and should not be read as guaranteed accuracy. With policy-001, a category or priority score below 0.60 requires review. On the 81-ticket test set, 58 tickets required review. Even a high score can be wrong.

Explanations are shown for new predictions from the explanation-enabled bundle. Earlier saved records may say explanations unavailable. That does not change their original saved recommendation.

## 5. Inspect history

Choose History and select a ticket. View its redacted text, original result, scores, explanation when available, owner and versions. Refresh loads recent records; Load more retrieves the next page. A viewer sees only their own predictions. Operators and maintainers can inspect the shared demonstration history.

Records with PERFORMANCE DEMO subjects were created by the bounded performance check. They are artificial traffic and should be identified as such in analysis.

## 6. Submit feedback - operator or maintainer

1. Select a prediction in History.
2. Use its feedback form. Choose only category and/or priority labels you actually reviewed; leave the other target Not reviewed.
3. Enter a reason. Keep the practice-correction setting selected for a synthetic demonstration.
4. Inspect the confirmation preview, then save once.
5. Find the submission in Feedback. It starts Pending review.

A submitted correction does not rewrite the original prediction or immediately retrain a model. An unreviewed model label is not ground truth.

## 7. Review feedback - maintainer

Open Feedback and choose a pending submission from another account. Inspect the original ticket and proposed labels. Enter a decision reason, choose Approve or Reject, inspect the confirmation and confirm. The saved decision displays reviewer and time. A repeated decision is blocked, and you cannot review your own submission.

Approval makes a label eligible for an explicitly selected snapshot; it does not automatically replace a running model. Practice labels remain marked synthetic_demo.

## 8. Pipeline console - maintainer

The Pipeline screen displays the real Spark ETL -> Train -> Evaluate workflow. Acquisition, preparation, split IDs and selected model settings are already versioned inputs. The current console does not perform new feedback-candidate training or deployment.

An authorized terminal worker must be running. A maintainer starts it from the repository with the AIops environment active:

```bash
python -m scripts.pipeline_worker --once
```

Enter maintainer credentials privately. --once waits for and processes one job, then exits. Do not run separate manual training commands at the same time.

In the browser, enter a run reason. Leave Rebuild all stages unchecked to reuse unchanged results; select it for actual stage execution. Click Start pipeline. Only one queued, running or cancellation-requested job is allowed. A queued job waits until the worker is available.

Stage statuses mean Pending, Running, Succeeded, Reused, Failed, Cancelled, Interrupted or Skipped. Reused means the existing outputs were unchanged; it is not a fresh training run. Counts and elapsed seconds describe the recorded stage. The validation gate result is separate from deployment, and a successful job leaves the serving release unchanged.

To cancel, select the active job, enter a cancellation reason and confirm Request cancellation. A queued job cancels immediately. A running job first says Cancellation requested while the worker stops and cleans up. Wait for its final state before starting another job.

To retry a finished job, select it, click Prepare retry, review the reason/rebuild choice and start the retry. A new job ID links to the original. After an interrupted/cancelled job, a forced rebuild restores working pipeline outputs.

## 9. Monitoring

Grafana: http://127.0.0.1:3001/d/aiopsdesk-overview. Use the separate Grafana account; it is not the application maintainer account. Prometheus: http://127.0.0.1:9090.

Dashboards show API/model-call signals, host resources and saved report summaries. Scrapes occur every 15 seconds, so a change can take a scrape interval to appear. Report age shows how long ago CI, a pipeline job or a drift check ran. Scraping a report does not rerun its analysis. Insufficient data is an undetermined drift result, not a healthy/no-drift conclusion.

## 10. Troubleshooting

| What you see | What to do |
| --- | --- |
| Service unavailable | Wait briefly and retry. Maintainer checks Compose status and model/API logs. |
| Invalid or missing input | Read the field message; supply both text fields within 5000 combined characters. |
| Prediction seems wrong | Inspect its explanation and ask an operator to submit reviewed feedback. |
| History or Pipeline looks stale | Read the freshness time. Restore the connection; polling resumes while the tab is visible. |
| Job stays queued | Start an authenticated terminal worker. Check that another job is not active. |
| Cancellation requested persists | Inspect the worker terminal. Do not clear a database lock or start competing training blindly. |
| Prometheus query has no data | Clear its fixed evaluation timestamp, execute again, and inspect targets. |
| Frontend port already used | Stop the project Vite development server before publishing Docker port 3002; do not kill unrelated services. |

## 11. Maintainer startup and shutdown

From the initialized repository, with the existing local images and application database volume:

```bash
docker compose --profile observe up -d --wait --wait-timeout 180
docker compose --profile observe ps
curl --fail --silent --show-error http://127.0.0.1:3002/api/health/ready
```

Expected release: candidate-001 / policy-001. The model image includes the explanations-001 serving capability. MLflow tracking is optional and starts separately with bash scripts/start_mlflow.sh. It can remain stopped during ordinary predictions.

Stop the terminal worker with Ctrl+C when idle, then stop project services while retaining their storage:

```bash
docker compose --profile observe stop
```

Keep the Minikube profile stopped during normal Compose use. Avoid docker compose down -v: removing monitoring volumes loses their history; the application database is separately stored in an external named volume.

For fresh-checkout restoration, offline backups, account initialization and document rebuilding, see reproduction.md. For demo sequence and limitations, see demo-guide.md and limitations.md.
