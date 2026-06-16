import { exportReport, logEvent } from '../api/client'

export default function ExportButton({ report }) {
  function handleClick() {
    exportReport(report)
    logEvent({ thread_id: report.thread_id, ticker: report.ticker, event_type: 'exported' }).catch(() => {})
  }

  return (
    <button
      onClick={handleClick}
      className="border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50 text-sm"
    >
      Export PDF
    </button>
  )
}
