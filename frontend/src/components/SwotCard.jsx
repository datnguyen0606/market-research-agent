const QUADRANTS = [
  { key: 'strengths',     label: 'Strengths',     bg: 'bg-green-50',  border: 'border-green-200', text: 'text-green-800' },
  { key: 'weaknesses',    label: 'Weaknesses',    bg: 'bg-red-50',    border: 'border-red-200',   text: 'text-red-800' },
  { key: 'opportunities', label: 'Opportunities', bg: 'bg-blue-50',   border: 'border-blue-200',  text: 'text-blue-800' },
  { key: 'threats',       label: 'Threats',       bg: 'bg-orange-50', border: 'border-orange-200',text: 'text-orange-800' },
]

export default function SwotCard({ swot }) {
  const data = swot || {}
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
      {QUADRANTS.map(({ key, label, bg, border, text }) => (
        <div key={key} className={`${bg} border ${border} rounded-lg p-4`}>
          <h4 className={`font-semibold text-sm ${text} mb-2 uppercase tracking-wide`}>{label}</h4>
          <ul className="space-y-1">
            {(data[key] || []).map((item, i) => (
              <li key={i} className="text-sm text-gray-700 flex gap-2">
                <span className="mt-1 shrink-0">•</span>
                <span>{item}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}
