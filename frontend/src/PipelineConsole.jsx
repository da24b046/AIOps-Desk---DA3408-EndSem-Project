import { useEffect, useRef, useState } from 'react'
import { apiRequest } from './api'

const activeStates = ['queued', 'running', 'cancel_requested']
const labels = {
  queued: 'Queued',
  running: 'Running',
  cancel_requested: 'Cancellation requested',
  succeeded: 'Succeeded',
  failed: 'Failed',
  cancelled: 'Cancelled',
  interrupted: 'Interrupted',
  pending: 'Pending',
  skipped: 'Skipped',
  reused: 'Reused',
}
const errors = {
  stage_failed: 'A stage failed. Further stages were stopped. Inspect the worker log for details.',
  stage_timeout: 'A stage exceeded its time limit and its processes were stopped.',
  worker_interrupted: 'The worker was interrupted before completion.',
  worker_connection_lost: 'The worker lost API communication and stopped execution.',
  quality_gate_failed: 'Evaluation completed, but the quality gate did not pass.',
}
const countLabels = {
  input_rows: 'Input rows',
  retained_rows: 'Retained rows',
  rejected_rows: 'Excluded rows',
  train_rows: 'Training rows',
  validation_rows: 'Validation rows',
}

function localTime(value) {
  return value
    ? new Date(value).toLocaleString(undefined, { timeZoneName: 'short' })
    : '—'
}

export default function PipelineConsole({ token, onSessionExpired }) {
  const [items, setItems] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [job, setJob] = useState(null)
  const [checked, setChecked] = useState(null)
  const [pollError, setPollError] = useState('')
  const [error, setError] = useState('')
  const [reason, setReason] = useState('')
  const [force, setForce] = useState(false)
  const [retryOf, setRetryOf] = useState(null)
  const [cancelReason, setCancelReason] = useState('')
  const [saving, setSaving] = useState(false)
  const inFlight = useRef(false)

  useEffect(() => {
    let active = true
    let fetching = false

    async function refresh() {
      if (!active || fetching || document.hidden) return
      fetching = true
      try {
        const [history, detail] = await Promise.all([
          apiRequest('/v1/pipeline-runs?limit=20', { token }),
          selectedId
            ? apiRequest(`/v1/pipeline-runs/${selectedId}`, { token })
            : Promise.resolve(null),
        ])
        if (!active) return
        setItems(history.items)
        setJob(detail)
        setChecked(new Date())
        setPollError('')
        if (!selectedId && history.items.length) {
          setSelectedId(history.items[0].job_id)
        }
      } catch (failure) {
        if (!active) return
        setPollError(failure.message)
        if (failure.status === 401) onSessionExpired()
      } finally {
        fetching = false
      }
    }

    refresh()
    const timer = setInterval(refresh, 2000)
    document.addEventListener('visibilitychange', refresh)
    return () => {
      active = false
      clearInterval(timer)
      document.removeEventListener('visibilitychange', refresh)
    }
  }, [token, selectedId, onSessionExpired])

  async function perform(action) {
    if (inFlight.current) return
    inFlight.current = true
    setSaving(true)
    setError('')
    try {
      await action()
    } catch (failure) {
      setError(failure.message)
      if (failure.status === 401) onSessionExpired()
    } finally {
      inFlight.current = false
      setSaving(false)
    }
  }

  function start(event) {
    event.preventDefault()
    perform(async () => {
      if (!reason.trim()) throw new Error('Enter a reason for this run.')
      const body = { reason: reason.trim(), force_rebuild: force }
      if (retryOf) body.retry_of = retryOf
      const created = await apiRequest('/v1/pipeline-runs', {
        method: 'POST', token, body,
      })
      setItems((current) => [created, ...current].slice(0, 20))
      setSelectedId(created.job_id)
      setJob(created)
      setReason('')
      setRetryOf(null)
      setForce(false)
      setCancelReason('')
    })
  }

  function cancel() {
    if (!cancelReason.trim()) {
      setError('Enter a reason for cancellation.')
      return
    }
    if (!window.confirm('Request cancellation? The worker will stop the active stage.')) return
    perform(async () => {
      const updated = await apiRequest(
        `/v1/pipeline-runs/${job.job_id}/cancel`,
        {
          method: 'POST', token,
          body: { reason: cancelReason.trim() },
        }
      )
      setJob(updated)
      setItems((current) => current.map((item) =>
        item.job_id === updated.job_id ? updated : item
      ))
      setCancelReason('')
    })
  }

  const hasActive = items.some((item) => activeStates.includes(item.status))
  const selected = job?.job_id === selectedId ? job : null
  const canStart = !saving && !hasActive && Boolean(checked) && !pollError

  return (
    <>
      {error && <div className="error" role="alert">{error}</div>}
      {pollError && (
        <div className="error" role="alert">
          Updates unavailable: {pollError} Displayed records may be stale.
        </div>
      )}
      <p className="freshness">
        Last successful update: {checked ? localTime(checked) : 'Waiting…'}.
        {' '}Updates every two seconds while this tab is visible.
      </p>

      <div className="history-layout">
        <section className="card history-card">
          <h2>Pipeline jobs</h2>
          <p>Prepare and evaluate working models. These jobs do not deploy a model.</p>
          <p className="notice review">
            A terminal worker must be running to process queued jobs.
          </p>

          <form onSubmit={start}>
            <fieldset disabled={saving}>
              <label htmlFor="pipeline-reason">Run reason</label>
              <textarea id="pipeline-reason" required maxLength={200}
                value={reason} onChange={(event) => setReason(event.target.value)} />
              <label className="pipeline-checkbox">
                <input type="checkbox" checked={force}
                  onChange={(event) => setForce(event.target.checked)} />
                Rebuild all stages instead of reusing unchanged results
              </label>
              {retryOf && (
                <p>
                  Retry prepared for the selected previous job.
                  {' '}
                  <button type="button" className="secondary"
                    onClick={() => setRetryOf(null)}>Clear retry</button>
                </p>
              )}
              <button type="submit" disabled={!canStart}>
                {saving ? 'Saving…' : retryOf ? 'Start retry' : 'Start pipeline'}
              </button>
            </fieldset>
          </form>

          {hasActive && <p role="status">One job is active. Another cannot start yet.</p>}
          <h3>Recent jobs</h3>
          {!checked && !pollError && <p>Loading jobs…</p>}
          {checked && items.length === 0 && <p>No pipeline jobs yet.</p>}
          <div className="ticket-list">
            {items.map((item) => (
              <button key={item.job_id} type="button" className="ticket-item"
                disabled={saving} aria-pressed={selectedId === item.job_id}
                onClick={() => {
                  setSelectedId(item.job_id)
                  setCancelReason('')
                  setRetryOf(null)
                  setError('')
                }}>
                <strong>{labels[item.status] ?? item.status}</strong>
                <span>{item.reason}</span>
                <small>{localTime(item.created_at)}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="card history-details">
          <h2>Pipeline progress</h2>
          {!selected ? <p>Select a job to inspect its stages.</p> : (
            <>
              <p className={`pipeline-state state-${selected.status}`} role="status">
                <strong>{labels[selected.status]}</strong>
              </p>
              <p>{selected.reason}</p>
              <p className="muted">
                Versioned dataset and fixed split IDs → Spark ETL → Train → Evaluate.
                Acquisition and splitting are prepared inputs.
              </p>

              <ol className="pipeline-stages">
                {selected.stages.map((stage) => (
                  <li key={stage.id} data-status={stage.status}>
                    <h3>{stage.label}</h3>
                    <strong>{labels[stage.status] ?? stage.status}</strong>
                    <p>{stage.elapsed_seconds == null
                      ? 'Duration not recorded yet'
                      : `${stage.elapsed_seconds.toFixed(2)} seconds`}</p>
                    <dl>
                      {Object.entries(stage.counts).map(([key, value]) => (
                        <div key={key}>
                          <dt>{countLabels[key] ?? key}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                    </dl>
                    {stage.status === 'succeeded'
                      && stage.counts.input_rows != null
                      && stage.elapsed_seconds > 0 && (
                        <p className="muted">
                          {(stage.counts.input_rows / stage.elapsed_seconds).toFixed(1)}
                          {' '}input rows/s including stage checks and execution.
                        </p>
                    )}
                    {stage.status === 'reused' && (
                      <p className="muted">Outputs verified unchanged; training was not rerun.</p>
                    )}
                  </li>
                ))}
              </ol>

              {selected.error_code && (
                <div className="error" role="alert">
                  {errors[selected.error_code] ?? 'The job did not finish successfully.'}
                </div>
              )}

              {selected.summary.quality_gate_passed === true && (
                <div className="notice ready">
                  <strong>Validation quality gate passed</strong>
                  <p>Category macro-F1: {selected.summary.category_macro_f1?.toFixed(4)}</p>
                  <p>Priority macro-F1: {selected.summary.priority_macro_f1?.toFixed(4)}</p>
                  <p>The serving release is unchanged.</p>
                </div>
              )}

              {['queued', 'running'].includes(selected.status) && (
                <div className="feedback-panel">
                  <label htmlFor="pipeline-cancel-reason">Cancellation reason</label>
                  <input id="pipeline-cancel-reason" maxLength={200}
                    disabled={saving} value={cancelReason}
                    onChange={(event) => setCancelReason(event.target.value)} />
                  <button type="button" className="secondary"
                    disabled={saving || Boolean(pollError)} onClick={cancel}>
                    Request cancellation
                  </button>
                </div>
              )}

              {selected.status === 'cancel_requested' && (
                <p className="notice review">
                  Waiting for the worker to stop and acknowledge cancellation.
                  The job remains active until then.
                </p>
              )}

              {!activeStates.includes(selected.status) && (
                <button type="button" className="secondary"
                  disabled={!canStart}
                  onClick={() => {
                    setRetryOf(selected.job_id)
                    setReason('Retry of previous pipeline job')
                    setError('')
                  }}>
                  Prepare retry
                </button>
              )}

              <details>
                <summary>Job details</summary>
                <dl className="details">
                  <dt>Job ID</dt><dd>{selected.job_id}</dd>
                  <dt>Requested by</dt><dd>{selected.requested_by}</dd>
                  <dt>Started</dt><dd>{localTime(selected.started_at)}</dd>
                  <dt>Finished</dt><dd>{localTime(selected.finished_at)}</dd>
                  <dt>Configuration</dt><dd>{selected.config_version}</dd>
                  {selected.retry_of && <><dt>Retry of</dt><dd>{selected.retry_of}</dd></>}
                  {selected.cancel_reason && (
                    <><dt>Cancellation reason</dt><dd>{selected.cancel_reason}</dd></>
                  )}
                </dl>
              </details>
            </>
          )}
        </section>
      </div>
    </>
  )
}
