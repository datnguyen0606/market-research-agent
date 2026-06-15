const NODE_LABELS = {
  router: 'Routing request…',
  document_rag: 'Searching documents…',
  market_search: 'Searching market data…',
  analyst: 'Analysing financials…',
  critic: 'Validating report…',
}

const STEPS = ['router', 'document_rag', 'market_search', 'analyst', 'critic']

export default function ProgressIndicator({ currentNode }) {
  const currentIdx = STEPS.indexOf(currentNode)
  const label = NODE_LABELS[currentNode] || 'Processing…'

  return (
    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
      <div className="flex items-center gap-3 mb-3">
        <svg className="animate-spin h-5 w-5 text-blue-600" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
        </svg>
        <span className="text-blue-800 font-medium">{label}</span>
      </div>
      <div className="flex gap-1">
        {STEPS.map((step, i) => (
          <div
            key={step}
            className={`h-1.5 flex-1 rounded ${
              i < currentIdx ? 'bg-blue-500' : i === currentIdx ? 'bg-blue-400 animate-pulse' : 'bg-blue-100'
            }`}
          />
        ))}
      </div>
    </div>
  )
}
