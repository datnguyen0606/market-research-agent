import { exportReport } from '../api/client'

export default function ExportButton({ report }) {
  return (
    <button
      onClick={() => exportReport(report)}
      className="border border-gray-300 text-gray-700 px-4 py-2 rounded hover:bg-gray-50 text-sm"
    >
      Export PDF
    </button>
  )
}
