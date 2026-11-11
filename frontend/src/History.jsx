import PredictionExplanation from './PredictionExplanation'
import { useEffect, useRef, useState } from 'react'
import { apiRequest } from './api'
import FeedbackForm from './FeedbackForm'

export default function History({ token, user, onSessionExpired }) {
  const [items, setItems] = useState([])
  const [cursor, setCursor] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [updated, setUpdated] = useState(null)
  const inFlight = useRef(false)

  useEffect(() => {
    let active = true

    async function loadInitial() {
      try {
        const data = await apiRequest('/v1/predictions?limit=10', { token })
        if (!active) return
        setItems(data.items)
        setCursor(data.next_cursor)
        setUpdated(new Date())
      } catch (failure) {
        if (!active) return
        setError(failure.message)
        if (failure.status === 401) onSessionExpired()
      } finally {
        if (active) setLoading(false)
      }
    }

    loadInitial()
    return () => { active = false }
  }, [token, onSessionExpired])

  async function loadPage(append) {
    if (inFlight.current) return
    inFlight.current = true
    setLoading(true)
    setError('')

    try {
      const query = new URLSearchParams({ limit: '10' })
      if (append && cursor !== null) query.set('cursor', String(cursor))

      const data = await apiRequest(`/v1/predictions?${query}`, { token })
      setItems((current) => append ? [...current, ...data.items] : data.items)
      setCursor(data.next_cursor)
      setUpdated(new Date())
      if (!append) setSelected(null)
    } catch (failure) {
      setError(failure.message)
      if (failure.status === 401) onSessionExpired()
    } finally {
      inFlight.current = false
      setLoading(false)
    }
  }

  return (
    <div className="history-layout">
      <section className="card history-card">
        <div className="section-heading">
          <h2>{user.role === 'viewer' ? 'Your ticket history' : 'Ticket review history'}</h2>
          <button className="secondary" type="button" disabled={loading}
            onClick={() => loadPage(false)}>
            Refresh
          </button>
        </div>

        <p className="muted">
          {user.role === 'viewer'
            ? 'Only tickets you submitted appear here.'
            : 'Inspect tickets before submitting or reviewing corrections.'}
        </p>

        {error && <div className="error" role="alert">{error}</div>}
        {loading && <p role="status">Loading tickets…</p>}
        {!loading && !error && items.length === 0 && (
          <p className="muted">No tickets yet. Submit one from Analyse.</p>
        )}

        <div className="ticket-list">
          {items.map((item) => (
            <button key={item.prediction_id} type="button"
              className="ticket-item"
              aria-pressed={selected?.prediction_id === item.prediction_id}
              onClick={() => setSelected(item)}>
              <strong>{item.redacted_input.subject}</strong>
              <span>{item.result.category} · {item.result.priority}</span>
              <small>
                {new Date(item.created_at).toLocaleString()} ·{' '}
                {item.owner_username ?? 'Earlier demonstration'}
              </small>
              {item.result.needs_review && <span>! Manual review required</span>}
            </button>
          ))}
        </div>

        {cursor !== null && (
          <button className="secondary load-more" type="button"
            disabled={loading} onClick={() => loadPage(true)}>
            Load more
          </button>
        )}

        {updated && (
          <p className="muted">
            Last loaded: {updated.toLocaleTimeString()}
          </p>
        )}
      </section>

      <section className="card history-details" aria-live="polite">
        <h2>Ticket details</h2>
        {!selected ? (
          <p className="muted">Select a ticket to inspect its saved recommendation.</p>
        ) : (
          <>
            <h3>{selected.redacted_input.subject}</h3>
            <p className="ticket-description">{selected.redacted_input.description}</p>

            <div className={`notice ${selected.result.needs_review ? 'review' : 'ready'}`}>
              <strong>
                {selected.result.needs_review
                  ? 'Manual review required'
                  : 'Saved recommendation'}
              </strong>
            </div>

            <dl className="result-grid">
              <div><dt>Category</dt><dd>{selected.result.category}</dd></div>
              <div><dt>Priority</dt><dd>{selected.result.priority}</dd></div>
              <div className="wide">
                <dt>Suggested team</dt><dd>{selected.result.team}</dd>
              </div>
              <div>
                <dt>Category score (0–1)</dt>
                <dd>{selected.result.category_score.toFixed(3)}</dd>
              </div>
              <div>
                <dt>Priority score (0–1)</dt>
                <dd>{selected.result.priority_score.toFixed(3)}</dd>
              </div>
            </dl>

            <PredictionExplanation explanation={selected.result.explanation} />
            <details>
              <summary>Saved prediction details</summary>
              <dl className="details">
                <dt>Prediction ID</dt><dd>{selected.prediction_id}</dd>
                <dt>Owner</dt><dd>{selected.owner_username ?? 'Not recorded'}</dd>
                <dt>Model</dt><dd>{selected.model_version}</dd>
                <dt>Policy</dt><dd>{selected.policy_version}</dd>
              </dl>
            </details>
            {['operator', 'maintainer'].includes(user.role) && (
              <FeedbackForm key={selected.prediction_id}
                ticket={selected} token={token}
                onSessionExpired={onSessionExpired} />
            )}
          </>
        )}
      </section>
    </div>
  )
}
