import MetricsPanel from './MetricsPanel'
import SwotCard from './SwotCard'
import SentimentBadge from './SentimentBadge'
import ExportButton from './ExportButton'
import ChatPanel from './ChatPanel'

export default function ReportDashboard({ report, onRegenerate, onReportUpdate }) {
  const rd = report.report_data || {}

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold text-gray-900">{report.company_name}</h2>
          <p className="text-gray-500 text-sm">
            {report.ticker} · {report.timestamp ? new Date(report.timestamp).toLocaleString() : ''}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <SentimentBadge sentiment={rd.market_sentiment} />
          <ExportButton report={report} />
          <button
            onClick={onRegenerate}
            className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 text-sm"
          >
            Regenerate
          </button>
        </div>
      </div>

      {/* Validation warning */}
      {!report.validation_passed && (
        <div className="bg-yellow-50 border border-yellow-300 rounded-lg p-3 text-sm text-yellow-800">
          ⚠ {report.validation_warning || 'Report did not pass full quality validation. Verify figures independently.'}
        </div>
      )}

      {/* Financial Metrics */}
      <section>
        <h3 className="text-lg font-semibold text-gray-800 mb-3">Financial Metrics</h3>
        <MetricsPanel metrics={rd.financial_metrics} />
      </section>

      {/* Executive Summary */}
      <section>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-semibold text-gray-800">Executive Summary</h3>
          <button
            onClick={() => navigator.clipboard.writeText(rd.executive_summary || '')}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Copy
          </button>
        </div>
        <p className="text-gray-700 leading-relaxed">{rd.executive_summary}</p>
      </section>

      {/* SWOT */}
      <section>
        <h3 className="text-lg font-semibold text-gray-800 mb-3">SWOT Analysis</h3>
        <SwotCard swot={rd.swot_analysis} />
      </section>

      <p className="text-xs text-gray-400">
        Validation cycles: {rd.critic_iterations ?? '—'}
      </p>

      {/* Chat */}
      {report.thread_id && (
        <section>
          <h3 className="text-lg font-semibold text-gray-800 mb-3">Refine with Chat</h3>
          <ChatPanel threadId={report.thread_id} onReportUpdate={onReportUpdate} />
        </section>
      )}
    </div>
  )
}
