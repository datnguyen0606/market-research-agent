function MetricCard({ label, value, unit }) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-4">
      <p className="text-xs text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className="text-2xl font-bold text-gray-900">
        {value != null ? value.toLocaleString() : '—'}
        {value != null && unit && <span className="text-sm font-normal text-gray-500 ml-1">{unit}</span>}
      </p>
    </div>
  )
}

export default function MetricsPanel({ metrics }) {
  const fm = metrics || {}
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <MetricCard label="Revenue" value={fm.revenue_vnd_billions} unit="VND B" />
      <MetricCard label="Net Profit" value={fm.net_profit_vnd_billions} unit="VND B" />
      <MetricCard label="Net Margin" value={fm.margin_percentage} unit="%" />
    </div>
  )
}
