const baseURL = (window.AIOPS_CONFIG?.API_BASE_URL ?? '/api').replace(/\/$/, '')

export async function apiRequest(path, { method = 'GET', body, token } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 8000)

  try {
    const headers = { Accept: 'application/json' }
    if (body !== undefined) headers['Content-Type'] = 'application/json'
    if (token) headers.Authorization = `Bearer ${token}`

    const response = await fetch(`${baseURL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })

    const data = response.status === 204
      ? null
      : await response.json().catch(() => null)

    if (!response.ok) {
      const detail = data?.detail
      const message = Array.isArray(detail)
        ? detail.map((item) =>
            `${item.loc.filter((part) => part !== 'body').join('.')}: ${item.msg}`
          ).join('; ')
        : typeof detail === 'string'
          ? detail
          : `Request failed (${response.status}).`

      const error = new Error(message)
      error.status = response.status
      throw error
    }

    if (response.status !== 204 && data === null) {
      throw new Error('The server returned an unreadable response.')
    }
    return data
  } catch (error) {
    if (error.name === 'AbortError' || error instanceof TypeError) {
      const failure = new Error(
        error.name === 'AbortError'
          ? 'The request timed out. Please try again.'
          : 'Cannot reach the service. Check the connection and retry.'
      )
      failure.network = true
      throw failure
    }
    throw error
  } finally {
    clearTimeout(timer)
  }
}
