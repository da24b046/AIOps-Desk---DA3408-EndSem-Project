import { useEffect, useRef, useState } from 'react'
import { apiRequest } from './api'

export default function FeedbackForm({ ticket, token, onSessionExpired }) {
  const [category, setCategory] = useState('')
  const [priority, setPriority] = useState('')
  const [reason, setReason] = useState('')
  const [practice, setPractice] = useState(true)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(null)
  const inFlight = useRef(false)
  const stageHeading = useRef(null)

  useEffect(() => {
    if (confirming || saved) stageHeading.current?.focus()
  }, [confirming, saved])

  async function submit(event) {
    event.preventDefault()
    setError('')

    if (!category && !priority) {
      setError('Select at least one label to confirm or correct.')
      return
    }
    if (!reason.trim()) {
      setError('Explain why you are submitting this correction.')
      return
    }
    if (!confirming) {
      setConfirming(true)
      return
    }
    if (inFlight.current) return

    inFlight.current = true
    setBusy(true)

    try {
      const body = {
        prediction_id: ticket.prediction_id,
        reason: reason.trim(),
        label_source: practice ? 'synthetic_demo' : 'operator_review',
      }
      if (category) body.category = category
      if (priority) body.priority = priority

      const feedback = await apiRequest('/v1/feedback', {
        method: 'POST', token, body,
      })
      setSaved(feedback)
    } catch (failure) {
      setError(failure.message)
      if (failure.status === 401) onSessionExpired()
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  if (saved) {
    return (
      <section className="feedback-panel">
        <h3 ref={stageHeading} tabIndex={-1}>Correction saved</h3>
        <div className="notice ready">
          <strong>Pending maintainer review</strong>
          <p>The original prediction is unchanged. The running model has not changed.</p>
        </div>
        <dl className="details">
          <dt>Proposed category</dt>
          <dd>{saved.labels.category ?? 'Not supplied'}</dd>
          <dt>Proposed priority</dt>
          <dd>{saved.labels.priority ?? 'Not supplied'}</dd>
          <dt>Source</dt>
          <dd>{saved.label_source === 'synthetic_demo'
            ? 'Practice correction' : 'Operator-reviewed labels'}</dd>
          <dt>Feedback ID</dt><dd>{saved.feedback_id}</dd>
        </dl>
      </section>
    )
  }

  return (
    <section className="feedback-panel">
      <h3>Confirm or correct labels</h3>
      <p className="muted">
        Select only labels you reviewed. Choose the current value to confirm it.
      </p>

      {error && <div className="error" role="alert">{error}</div>}

      <form onSubmit={submit}>
        {!confirming ? (
          <fieldset disabled={busy}>
            <label htmlFor="feedback-category">Reviewed category</label>
            <select id="feedback-category" value={category}
              onChange={(event) => setCategory(event.target.value)}>
              <option value="">Not reviewed</option>
              {['Software', 'Account', 'Network', 'Security'].map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>

            <label htmlFor="feedback-priority">Reviewed priority</label>
            <select id="feedback-priority" value={priority}
              onChange={(event) => setPriority(event.target.value)}>
              <option value="">Not reviewed</option>
              <option value="Medium">Medium</option>
              <option value="High">High</option>
            </select>

            <label htmlFor="feedback-reason">Reason</label>
            <textarea id="feedback-reason" rows={3} required maxLength={500}
              value={reason}
              onChange={(event) => setReason(event.target.value)} />
            <p className="muted">Explain the correction without sensitive details.</p>

            <label className="checkbox-row">
              <input type="checkbox" checked={practice}
                onChange={(event) => setPractice(event.target.checked)} />
              <span>Practice correction</span>
            </label>
            <p className="muted">
              Keep this enabled for demonstrations. Practice labels stay separate
              from ordinary operator-reviewed labels.
            </p>

            <button type="submit">Review correction</button>
          </fieldset>
        ) : (
          <div className="feedback-preview">
            <h4 ref={stageHeading} tabIndex={-1}>Confirm your submission</h4>
            <p>
              <strong>Original:</strong> {ticket.result.category}
              {' · '}{ticket.result.priority}
            </p>
            <p><strong>Reviewed category:</strong> {category || 'Not supplied'}</p>
            <p><strong>Reviewed priority:</strong> {priority || 'Not supplied'}</p>
            <p className="ticket-description"><strong>Reason:</strong> {reason}</p>
            <p><strong>Source:</strong> {practice
              ? 'Practice correction' : 'Operator-reviewed labels'}</p>
            <p className="muted">This will be saved as pending feedback.</p>

            <div className="feedback-actions">
              <button type="button" className="secondary" disabled={busy}
                onClick={() => setConfirming(false)}>
                Back to edit
              </button>
              <button type="submit" disabled={busy}>
                {busy ? 'Saving…' : 'Confirm and save'}
              </button>
            </div>
          </div>
        )}
      </form>
    </section>
  )
}
