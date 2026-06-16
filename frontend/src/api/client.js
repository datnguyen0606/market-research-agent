const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// ── SSE streaming helper (works for both GET and POST) ───────────────────────

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

// ── Report generation ────────────────────────────────────────────────────────

export function streamReport({ ticker, company_name, focus_areas = [], thread_id = null }) {
  const params = new URLSearchParams({ ticker, company_name, focus_areas: focus_areas.join(',') })
  if (thread_id) params.set('thread_id', thread_id)
  return streamSSE(`${BASE_URL}/api/v1/research/stream?${params}`)
}

// ── Chat follow-up ───────────────────────────────────────────────────────────

export function streamChat(thread_id, message) {
  return streamSSE(`${BASE_URL}/api/v1/research/chat/${thread_id}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}

// ── Document upload ──────────────────────────────────────────────────────────

export async function uploadDocument(ticker, file) {
  const form = new FormData()
  form.append('ticker', ticker)
  form.append('file', file)
  const res = await fetch(`${BASE_URL}/api/v1/documents/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Behavioral events (implicit feedback) ────────────────────────────────────

export async function logEvent(payload) {
  const res = await fetch(`${BASE_URL}/api/v1/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}

// ── PDF export (client-side) ─────────────────────────────────────────────────

export function exportReport(report) {
  import('jspdf').then(({ default: jsPDF }) => {
    const doc = new jsPDF({ unit: 'mm', format: 'a4' })
    const margin = 20
    let y = 20

    doc.setFont('helvetica', 'bold'); doc.setFontSize(18)
    doc.text(report.company_name || report.ticker, margin, y); y += 10

    doc.setFont('helvetica', 'normal'); doc.setFontSize(11)
    doc.text(`Ticker: ${report.ticker}`, margin, y); y += 7
    doc.text(`Generated: ${report.timestamp || new Date().toISOString()}`, margin, y); y += 10

    if (!report.validation_passed) {
      doc.setTextColor(180, 50, 50); doc.setFontSize(9)
      doc.text('⚠ Report did not pass full quality validation. Verify figures independently.', margin, y)
      doc.setTextColor(0, 0, 0); y += 8
    }

    const rd = report.report_data || {}
    doc.setFont('helvetica', 'bold'); doc.setFontSize(13)
    doc.text('Executive Summary', margin, y); y += 6
    doc.setFont('helvetica', 'normal'); doc.setFontSize(10)
    const summaryLines = doc.splitTextToSize(rd.executive_summary || '', 170)
    doc.text(summaryLines, margin, y); y += summaryLines.length * 5 + 8

    doc.setFont('helvetica', 'bold'); doc.setFontSize(13)
    doc.text('Financial Metrics', margin, y); y += 6
    doc.setFont('helvetica', 'normal'); doc.setFontSize(10)
    const fm = rd.financial_metrics || {}
    doc.text(`Revenue: ${fm.revenue_vnd_billions ?? '—'} VND B`, margin, y); y += 5
    doc.text(`Net Profit: ${fm.net_profit_vnd_billions ?? '—'} VND B`, margin, y); y += 5
    doc.text(`Margin: ${fm.margin_percentage ?? '—'}%`, margin, y); y += 10

    const swot = rd.swot_analysis || {}
    doc.setFont('helvetica', 'bold'); doc.setFontSize(13)
    doc.text('SWOT Analysis', margin, y); y += 6
    for (const [label, items] of [['Strengths', swot.strengths], ['Weaknesses', swot.weaknesses], ['Opportunities', swot.opportunities], ['Threats', swot.threats]]) {
      doc.setFont('helvetica', 'bold'); doc.setFontSize(10)
      doc.text(label, margin, y); y += 5
      doc.setFont('helvetica', 'normal')
      for (const item of (items || [])) {
        const lines = doc.splitTextToSize(`• ${item}`, 165)
        doc.text(lines, margin + 3, y); y += lines.length * 5
      }
      y += 3
    }

    doc.setFont('helvetica', 'bold'); doc.setFontSize(11)
    doc.text(`Market Sentiment: ${rd.market_sentiment || '—'}`, margin, y)
    doc.save(`${report.ticker}_report.pdf`)
  })
}
