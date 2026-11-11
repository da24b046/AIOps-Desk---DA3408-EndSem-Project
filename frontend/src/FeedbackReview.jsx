import { useEffect, useRef, useState } from 'react'
import { apiRequest } from './api'

const statusText = {
  pending: 'Pending review',
  approved: 'Approved',
  rejected: 'Rejected',
}

export default function FeedbackReview({ token, user, onSessionExpired }) {
  const [items, setItems] = useState([])
  const [cursor, setCursor] = useState(null)
  const [selected, setSelected] = useState(null)
  const [original, setOriginal] = useState(null)
  const [audit, setAudit] = useState(null)
  const [loading, setLoading] = useState(true)
  const [detailLoading, setDetailLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [reason, setReason] = useState('')
  const [decision, setDecision] = useState(null)
  const [error, setError] = useState('')
  const requestVersion = useRef(0)
  const inFlight = useRef(false)

  useEffect(() => {
    let active = true

    async function load() {
      try {
        const data = await apiRequest('/v1/feedback?limit=20', { token })
        if (active) {
          setItems(data.items)
          setCursor(data.next_cursor)
        }
      } catch (failure) {
        if (active) {
          setError(failure.message)
          if (failure.status === 401) onSessionExpired()
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    load()
    return () => { active = false }
  }, [token, onSessionExpired])

  async function loadMore() {
    if (loading || inFlight.current) return
    inFlight.current = true
    setLoading(true)
    setError('')
    try {
      const data = await apiRequest(
        `/v1/feedback?limit=20&cursor=${cursor}`, { token }
      )
      setItems((current) => [...current, ...data.items])
      setCursor(data.next_cursor)
    } catch (failure) {
      setError(failure.message)
      if (failure.status === 401) onSessionExpired()
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }

  async function openFeedback(item) {
    const version = ++requestVersion.current
    setSelected(item)
    setOriginal(null)
    setAudit(null)
    setReason('')
    setDecision(null)
    setError('')
    setDetailLoading(true)

    try {
      const [prediction, review] = await Promise.all([
        apiRequest(`/v1/predictions/${item.prediction_id}`, { token }),
        item.status === 'pending'
          ? Promise.resolve(null)
          : apiRequest(`/v1/feedback/${item.feedback_id}/review`, { token }),
      ])
      if (version !== requestVersion.current) return
      setOriginal(prediction)
      setAudit(review)
    } catch (failure) {
      if (version !== requestVersion.current) return
      setError(failure.message)
      if (failure.status === 401) onSessionExpired()
    } finally {
      if (version === requestVersion.current) setDetailLoading(false)
    }
  }

  function prepareDecision(value) {
    if (!reason.trim()) {
      setError('Enter a reason for your review decision.')
      return
    }
    setError('')
    setDecision(value)
  }

  async function saveDecision(event) {
    event.preventDefault()
    if (!decision || inFlight.current) return
    inFlight.current = true
    setSaving(true)
    setError('')

    try {
      const result = await apiRequest(
        `/v1/feedback/${selected.feedback_id}/review`,
        {
          method: 'POST',
          token,
          body: { decision, reason: reason.trim() },
        }
      )
      setAudit(result)
      setSelected((current) => ({ ...current, status: result.decision }))
      setItems((current) => current.map((item) =>
        item.feedback_id === result.feedback_id
          ? { ...item, status: result.decision }
          : item
      ))
      setDecision(null)
    } catch (failure) {
      setError(failure.message)
      if (failure.status === 401) onSessionExpired()
    } finally {
      inFlight.current = false
      setSaving(false)
    }
  }

  return (
    <>
      {error && <div className="error" role="alert">{error}</div>}
      <div className="history-layout">
        <section className="card history-card">
          <h2>{user.role === 'maintainer' ? 'Feedback review' : 'Your feedback'}</h2>
          <p className="muted">
            {user.role === 'maintainer'
              ? 'Inspect the original recommendation before deciding.'
              : 'Follow the status of your submitted corrections.'}
          </p>

          {loading && <p role="status">Loading feedback…</p>}
          {!loading && items.length === 0 && <p>No feedback submitted yet.</p>}

          <div className="ticket-list">
            {items.map((item) => (
              <button key={item.feedback_id} className="ticket-item"
                type="button" disabled={saving}
                aria-pressed={selected?.feedback_id === item.feedback_id}
                onClick={() => openFeedback(item)}>
                <strong>{statusText[item.status]}</strong>
                <span>
                  Category: {item.labels.category ?? 'Not reviewed'}
                  {' · '}Priority: {item.labels.priority ?? 'Not reviewed'}
                </span>
                <small>
                  By {item.author_username} · {new Date(item.created_at).toLocaleString()}
                </small>
                <small>{item.label_source === 'synthetic_demo'
                  ? 'Practice correction' : 'Operator-reviewed labels'}</small>
              </button>
            ))}
          </div>

          {cursor !== null && (
            <button className="secondary load-more" type="button"
              disabled={loading || saving} onClick={loadMore}>
              Load more
            </button>
          )}
        </section>

        <section className="card history-details" aria-live="polite">
          <h2>Correction details</h2>
          {!selected ? <p>Select a submission to inspect it.</p> : (
            <>
              <div className={`notice ${selected.status === 'approved' ? 'ready' : 'review'}`}>
                <strong>{statusText[selected.status]}</strong>
              </div>

              {detailLoading && <p role="status">Loading original ticket…</p>}
              {original && (
                <>
                  <h3>{original.redacted_input.subject}</h3>
                  <p className="ticket-description">
                    {original.redacted_input.description}
                  </p>
                  <dl className="result-grid">
                    <div><dt>Original category</dt><dd>{original.result.category}</dd></div>
                    <div><dt>Reviewed category</dt><dd>{selected.labels.category ?? 'Not supplied'}</dd></div>
                    <div><dt>Original priority</dt><dd>{original.result.priority}</dd></div>
                    <div><dt>Reviewed priority</dt><dd>{selected.labels.priority ?? 'Not supplied'}</dd></div>
                  </dl>
                </>
              )}

              <p className="ticket-description">
                <strong>Submission reason:</strong> {selected.reason}
              </p>
              <p><strong>Submitted by:</strong> {selected.author_username}</p>
              <p><strong>Source:</strong> {selected.label_source === 'synthetic_demo'
                ? 'Practice correction' : 'Operator-reviewed labels'}</p>

              {audit && (
                <div className="feedback-preview">
                  <h3>Recorded decision: {statusText[audit.decision]}</h3>
                  <p><strong>Reviewer:</strong> {audit.reviewer_username}</p>
                  <p className="ticket-description"><strong>Reason:</strong> {audit.reason}</p>
                  <p><strong>Reviewed:</strong> {new Date(audit.reviewed_at).toLocaleString()}</p>
                  <p className="muted">The deployed model is unchanged.</p>
                </div>
              )}

              {selected.status === 'pending' && user.role === 'maintainer' && (
                selected.author_username === user.username ? (
                  <p className="notice review">
                    Another maintainer must review your own submission.
                  </p>
                ) : original && (
                  <form className="feedback-panel" onSubmit={saveDecision}>
                    <h3>Review decision</h3>
                    <p className="muted">A recorded decision cannot be changed for this submission.</p>
                    <label htmlFor="review-reason">Decision reason</label>
                    <textarea id="review-reason" required maxLength={500}
                      disabled={saving || Boolean(decision)}
                      value={reason} onChange={(event) => setReason(event.target.value)} />

                    {!decision ? (
                      <div className="feedback-actions">
                        <button type="button" onClick={() => prepareDecision('approved')}>
                          Approve
                        </button>
                        <button type="button" className="secondary"
                          onClick={() => prepareDecision('rejected')}>
                          Reject
                        </button>
                      </div>
                    ) : (
                      <div className="feedback-preview">
                        <p><strong>Confirm decision:</strong> {statusText[decision]}</p>
                        <p className="ticket-description">{reason}</p>
                        <div className="feedback-actions">
                          <button type="button" className="secondary" disabled={saving}
                            onClick={() => setDecision(null)}>
                            Back to edit
                          </button>
                          <button type="submit" disabled={saving}>
                            {saving ? 'Saving…' : 'Confirm decision'}
                          </button>
                        </div>
                      </div>
                    )}
                  </form>
                )
              )}
            </>
          )}
        </section>
      </div>
    </>
  )
}
