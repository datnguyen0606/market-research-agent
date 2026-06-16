import { useState, useRef, useEffect } from 'react'
import { streamReport, logEvent } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import SearchBar from '../components/SearchBar'
import UploadDropzone from '../components/UploadDropzone'
import ProgressIndicator from '../components/ProgressIndicator'
import ReportDashboard from '../components/ReportDashboard'

export default function ResearchPage() {
  const { username, logout } = useAuth()
  const [ticker, setTicker] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentNode, setCurrentNode] = useState(null)
  const [report, setReport] = useState(null)       // single source of truth
  const [error, setError] = useState('')
  const abortRef = useRef(null)

  useEffect(() => () => abortRef.current?.abort(), [])

  async function startGeneration({ ticker: t, company_name, focus_areas = [], thread_id = null }) {
    abortRef.current?.abort()
    abortRef.current = new AbortController()

    setReport(null)
    setError('')
    setLoading(true)
    setCurrentNode(null)
    setTicker(t)

    try {
      for await (const event of streamReport({ ticker: t, company_name, focus_areas, thread_id })) {
        if (event.event === 'node_complete') {
          setCurrentNode(event.node)
        }
        if (event.event === 'done') {
          setReport(event)
          setCurrentNode(null)
          setLoading(false)
        }
        if (event.event === 'error') {
          setError(event.message)
          setCurrentNode(null)
          setLoading(false)
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setError(err.message || 'Failed to connect to the analysis service.')
        setLoading(false)
        setCurrentNode(null)
      }
    }
  }

  function handleReportUpdate(patch) {
    setReport(prev => prev ? { ...prev, ...patch } : prev)
  }

  async function handleRegenerate() {
    if (!report) return
    try {
      await logEvent({ thread_id: report.thread_id, ticker: report.ticker, event_type: 'regenerated' })
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

        {loading && !currentNode && (
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm text-blue-700 animate-pulse">
            Connecting to analysis service…
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-300 rounded-lg p-4 text-sm text-red-800">
            <p className="font-medium">Error</p>
            <p>{error}</p>
            <button onClick={() => setError('')} className="mt-2 text-xs text-red-600 hover:underline">
              Dismiss
            </button>
          </div>
        )}

        {report && (
          <ReportDashboard
            report={report}
            onRegenerate={handleRegenerate}
            onReportUpdate={handleReportUpdate}
          />
        )}
      </main>
    </div>
  )
}
