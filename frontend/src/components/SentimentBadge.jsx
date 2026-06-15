const STYLES = {
  Bullish: 'bg-green-100 text-green-800 border-green-300',
  Bearish: 'bg-red-100 text-red-800 border-red-300',
  Neutral: 'bg-gray-100 text-gray-700 border-gray-300',
}

export default function SentimentBadge({ sentiment }) {
  const style = STYLES[sentiment] || STYLES.Neutral
  return (
    <span className={`inline-block border rounded-full px-3 py-0.5 text-sm font-semibold ${style}`}>
      {sentiment || 'Unknown'}
    </span>
  )
}
