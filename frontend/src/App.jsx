import { useCallback, useEffect, useRef, useState } from 'react'
import { apiRequest } from './api'
import History from './History'
import FeedbackReview from './FeedbackReview'
import './App.css'

export default function App() {
  const [session, setSession] = useState(null)
  const [page, setPage] = useState('analyse')
  const [username, setUsername] = useState('operator')
  const [password, setPassword] = useState('')
  const [subject, setSubject] = useState('')
  const [description, setDescription] = useState('')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [connection, setConnection] = useState({
    status: 'checking', checked: null,
  })
  const inFlight = useRef(false)

  useEffect(() => {
    let active = true

    async function refreshHealth() {
      if (document.hidden) return
      let status = 'unavailable'
      try {
        await apiRequest('/health/ready')
        status = 'ready'
      } catch {
        // The visible status reports failed readiness checks.
      }
      if (active) setConnection({ status, checked: new Date() })
    }

    refreshHealth()
    const timer = setInterval(refreshHealth, 15000)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  const handleSessionExpired = useCallback(() => {
    setSession(null)
    setResult(null)
    setPage('analyse')
    setError('Your session expired. Please sign in again.')
  }, [])

  async function runAction(action) {
    if (inFlight.current) return
    inFlight.current = true
    setBusy(true)
    setError('')

    try {
      await action()
    } catch (failure) {
      if (session && failure.status === 401) {
        setSession(null)
        setResult(null)
        setError('Your session expired. Please sign in again.')
      } else {
        setError(failure.message)
      }
      if (failure.network || failure.status >= 500) {
        setConnection({ status: 'unavailable', checked: new Date() })
      }
    } finally {
      inFlight.current = false
      setBusy(false)
    }
  }

  function signIn(event) {
    event.preventDefault()
    runAction(async () => {
      const data = await apiRequest('/v1/session', {
        method: 'POST',
        body: { username: username.trim(), password },
      })
      setSession(data)
      setPassword('')
      setResult(null)
      setPage('analyse')
    })
  }

  function analyse(event) {
    event.preventDefault()
    runAction(async () => {
      setResult(null)
      if (!subject.trim() || !description.trim()) {
        throw new Error('Enter a subject and description.')
      }
      if (subject.length + description.length > 5000) {
        throw new Error('Keep the combined text within 5,000 characters.')
      }

      const data = await apiRequest('/v1/predict', {
        method: 'POST',
        token: session.access_token,
        body: { subject, description },
      })
      setResult(data)
    })
  }

  function signOut() {
    runAction(async () => {
      await apiRequest('/v1/session', {
        method: 'DELETE', token: session.access_token,
      })
      setSession(null)
      setResult(null)
    })
  }

  return (
    <div className="shell">
      <header className="header">
        <div>
          <p className="eyebrow">LOCAL IT SUPPORT</p>
          <h1>AIOpsDesk</h1>
          <p className="muted">Ticket classification and routing assistance</p>
        </div>
        <div className="header-actions">
          <span className={`badge ${connection.status}`}>
            Service {connection.status}
          </span>
          {session && (
            <>
              <span>{session.user.username} · {session.user.role}</span>
              <button className="secondary" disabled={busy} onClick={signOut}>
                Sign out
              </button>
            </>
          )}
        </div>
      </header>

      <p className="freshness">
        Last service check: {connection.checked
          ? connection.checked.toLocaleTimeString()
          : 'Waiting…'}
      </p>

      <main>
        {error && <div className="error" role="alert">{error}</div>}

        {!session ? (
          <section className="card login">
            <h2>Sign in</h2>
            <p className="muted">Use your local viewer, operator or maintainer account.</p>
            <form onSubmit={signIn}>
              <fieldset disabled={busy}>
                <label htmlFor="username">Username</label>
                <input id="username" autoComplete="username" required
                  value={username} onChange={(event) => setUsername(event.target.value)} />
                <label htmlFor="password">Password</label>
                <input id="password" type="password" autoComplete="current-password"
                  required value={password}
                  onChange={(event) => setPassword(event.target.value)} />
                <button type="submit">{busy ? 'Signing in…' : 'Sign in'}</button>
              </fieldset>
            </form>
          </section>
        ) : (
          <>
            <nav className="workspace-nav" aria-label="Workspace sections">
              <button type="button" disabled={busy}
                aria-current={page === 'analyse' ? 'page' : undefined}
                onClick={() => setPage('analyse')}>
                Analyse
              </button>
              <button type="button" disabled={busy}
                aria-current={page === 'history' ? 'page' : undefined}
                onClick={() => setPage('history')}>
                History
              </button>
              {['operator', 'maintainer'].includes(session.user.role) && (
                <button type="button" disabled={busy}
                  aria-current={page === 'feedback' ? 'page' : undefined}
                  onClick={() => setPage('feedback')}>
                  Feedback
                </button>
              )}
            </nav>
            {page === 'feedback' ? (
              <FeedbackReview token={session.access_token} user={session.user}
                onSessionExpired={handleSessionExpired} />
            ) : page === 'history' ? (
              <History token={session.access_token} user={session.user}
                onSessionExpired={handleSessionExpired} />
            ) : (
          <div className="workspace">
            <section className="card">
              <h2>Analyse a ticket</h2>
              <p className="muted">Describe the issue without passwords or sensitive information.</p>
              <form onSubmit={analyse}>
                <fieldset disabled={busy}>
                  <label htmlFor="subject">Subject</label>
                  <input id="subject" required maxLength={5000} value={subject}
                    onChange={(event) => setSubject(event.target.value)} />
                  <label htmlFor="description">Description</label>
                  <textarea id="description" required maxLength={5000}
                    rows={6} value={description}
                    onChange={(event) => setDescription(event.target.value)} />
                  <p className="muted">
                    {subject.length + description.length} / 5,000 characters
                  </p>
                  <button type="submit">{busy ? 'Analysing…' : 'Analyse ticket'}</button>
                </fieldset>
              </form>
            </section>

            <section className="card" aria-live="polite">
              <h2>Recommendation</h2>
              {!result ? (
                <p className="muted">
                  {busy ? 'Waiting for the result…' : 'Submit a ticket to see its recommendation.'}
                </p>
              ) : (
                <>
                  <div className={`notice ${result.result.needs_review ? 'review' : 'ready'}`}>
                    <strong>
                      {result.result.needs_review ? 'Manual review required' : 'Recommendation available'}
                    </strong>
                    <p>A support operator should confirm the suggested routing and priority.</p>
                  </div>
                  <dl className="result-grid">
                    <div><dt>Category</dt><dd>{result.result.category}</dd></div>
                    <div><dt>Priority</dt><dd>{result.result.priority}</dd></div>
                    <div className="wide"><dt>Suggested team</dt><dd>{result.result.team}</dd></div>
                    <div><dt>Category score (0–1)</dt><dd>{result.result.category_score.toFixed(3)}</dd></div>
                    <div><dt>Priority score (0–1)</dt><dd>{result.result.priority_score.toFixed(3)}</dd></div>
                  </dl>
                  <p className="muted">Higher scores indicate a stronger model preference.</p>
                  {result.result.review_reasons.length > 0 && (
                    <ul>
                      {result.result.review_reasons.map((reason) => (
                        <li key={reason}>
                          {reason === 'low_category_score'
                            ? 'The category suggestion has a low model score.'
                            : reason === 'low_priority_score'
                              ? 'The priority suggestion has a low model score.'
                              : 'The recommendation requires review.'}
                        </li>
                      ))}
                    </ul>
                  )}
                  <details>
                    <summary>Prediction details</summary>
                    <dl className="details">
                      <dt>Prediction ID</dt><dd>{result.prediction_id}</dd>
                      <dt>Model</dt><dd>{result.model_version}</dd>
                      <dt>Policy</dt><dd>{result.policy_version}</dd>
                      <dt>Created</dt>
                      <dd>{new Date(result.created_at).toLocaleString(undefined, {
                        timeZoneName: 'short',
                      })}</dd>
                    </dl>
                  </details>
                </>
              )}
            </section>
          </div>
            )}
          </>
        )}
      </main>
    </div>
  )
}
