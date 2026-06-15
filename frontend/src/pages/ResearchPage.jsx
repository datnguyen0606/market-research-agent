import { useState, useEffect, useRef } from 'react'
import { generateReport, pollReport, logFeedback } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import SearchBar from '../components/SearchBar'
import UploadDropzone from '../components/UploadDropzone'
import ProgressIndicator from '../components/ProgressIndicator'
import ReportDashboard from '../components/ReportDashboard'

const POLL_INTERVAL_MS = 2000
const TIMEOUT_MS = 5 * 60 * 1000 // 5 minutes

export default function ResearchPage() {
  const { username, logout } = useAuth()
  const [ticker, setTicker] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentNode, setCurrentNode] = useState(null)
  const [report, setReport] = useState(null)
  const [error, setError] = useState('')
  const [timedOut, setTimedOut] = useState(false)

  const pollRef = useRef(null)
  const timeoutRef = useRef(null)

  function clearPolling() {
    if (pollRef.current) clearInterval(pollRef.current)
    if (timeoutRef.current) clearTimeout(timeoutRef.current)
  }

  useEffect(() => () => clearPolling(), [])

  async function startGeneration(payload) {
    setReport(null)
    setError('')
    setTimedOut(false)
    setLoading(true)
    setTicker(payload.ticker)

    try {
      const { task_id } = await generateReport(payload)

      timeoutRef.current = setTimeout(() => {
        clearPolling()
        setLoading(false)
        setTimedOut(true)
        setCurrentNode(null)
      }, TIMEOUT_MS)

      pollRef.current = setInterval(async () => {
        try {
          const data = await pollReport(task_id)
          setCurrentNode(data.current_node || null)

          if (data.status === 'completed') {
            clearPolling()
            setLoading(false)
            setCurrentNode(null)
            setReport(data)
          } else if (data.status === 'failed') {
            clearPolling()
            setLoading(false)
            setCurrentNode(null)
            setError(data.error_message || 'Report generation failed.')
          }
        } catch (pollErr) {
          clearPolling()
          setLoading(false)
          setError(pollErr.message)
        }
      }, POLL_INTERVAL_MS)

    } catch (err) {
      setLoading(false)
      setError(err.message || 'Failed to start report generation.')
    }
  }

  async function handleRegenerate() {
    if (!report) return
    try {
      await logFeedback({
        task_id: report.task_id,
        langsmith_trace_id: 'n/a',
        action: 'report_regenerated',
        rating: null,
      })
    } catch { /* non-critical */ }
    startGeneration({ ticker: report.ticker, company_name: report.company_name, focus_areas: [] })
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-900">Market Research Agent</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">{username}</span>
          <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-700">Sign out</button>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <SearchBar onGenerate={startGeneration} loading={loading} />

        <UploadDropzone ticker={ticker} onIndexed={() => {}} />

        {loading && currentNode && <ProgressIndicator currentNode={currentNode} />}

        {timedOut && (
          <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-4 text-sm text-yellow-800">
            <p className="font-medium">Generation timed out after 5 minutes.</p>
            <p>Please try again.</p>
            <button
              onClick={() => { setTimedOut(false); startGeneration({ ticker, company_name: ticker, focus_areas: [] }) }}
              className="mt-2 bg-yellow-600 text-white px-3 py-1 rounded text-xs hover:bg-yellow-700"
            >
              Try Again
            </button>
          </div>
        )}

        {error && !timedOut && (
          <div className="bg-red-50 border border-red-300 rounded-lg p-4 text-sm text-red-800">
            <p className="font-medium">Error</p>
            <p>{error}</p>
            <button
              onClick={() => setError('')}
              className="mt-2 text-xs text-red-600 hover:underline"
            >
              Dismiss
            </button>
          </div>
        )}

        {report && <ReportDashboard report={report} onRegenerate={handleRegenerate} />}
      </main>
    </div>
  )
}
