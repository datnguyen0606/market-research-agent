const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── SSE streaming helper ──────────────────────────────────────────────────────

async function* streamSSE(url, options = {}) {
  const res = await fetch(url, options)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''
    for (const line of lines) {
      if (line.startsWith('data: ') && line.length > 6) {
        try { yield JSON.parse(line.slice(6)) } catch { /* skip malformed */ }
      }
    }
  }
}

// ── Research query ────────────────────────────────────────────────────────────

export function streamResearch({ query, thread_id = null }) {
  const params = new URLSearchParams({ query })
  if (thread_id) params.set('thread_id', thread_id)
  return streamSSE(`${BASE_URL}/api/v1/research/stream?${params}`)
}

// ── Chat follow-up ────────────────────────────────────────────────────────────

export function streamChat(thread_id, message) {
  return streamSSE(`${BASE_URL}/api/v1/research/chat/${thread_id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}

// ── Document upload ───────────────────────────────────────────────────────────

export async function uploadDocument(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/api/v1/documents/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Behavioral events ─────────────────────────────────────────────────────────

export async function logEvent(payload) {
  const res = await fetch(`${BASE_URL}/api/v1/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}
