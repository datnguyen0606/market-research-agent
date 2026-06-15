import { useState } from 'react'

export default function SearchBar({ onGenerate, loading }) {
  const [ticker, setTicker] = useState('')
  const [company, setCompany] = useState('')

  function handleSubmit(e) {
    e.preventDefault()
    if (!ticker.trim()) return
    onGenerate({ ticker: ticker.trim().toUpperCase(), company_name: company.trim() || ticker.trim().toUpperCase() })
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
      <input
        type="text"
        value={ticker}
        onChange={e => setTicker(e.target.value)}
        placeholder="Ticker (e.g. VNM)"
        className="border border-gray-300 rounded px-3 py-2 w-32 uppercase focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={loading}
        required
      />
      <input
        type="text"
        value={company}
        onChange={e => setCompany(e.target.value)}
        placeholder="Company name (optional)"
        className="border border-gray-300 rounded px-3 py-2 flex-1 focus:outline-none focus:ring-2 focus:ring-blue-500"
        disabled={loading}
      />
      <button
        type="submit"
        disabled={loading || !ticker.trim()}
        className="bg-blue-600 text-white px-5 py-2 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? 'Generating…' : 'Generate Report'}
      </button>
    </form>
  )
}
