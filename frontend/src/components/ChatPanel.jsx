import { useState, useRef, useEffect } from 'react'
import { streamChat } from '../api/client'

export default function ChatPanel({ threadId, onReportUpdate }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: text }])

    try {
      // chat_sent is logged server-side in chat_stream — it already has the run_id
      let assistantMsg = ''
      for await (const event of streamChat(threadId, text)) {
        if (event.event === 'node_complete') {
          // Could show a typing indicator per node if desired
        }
        if (event.event === 'done') {
          const rd = event.report_data || {}
          assistantMsg = rd.executive_summary || 'Report updated.'
          onReportUpdate?.({
            report_data: rd,
            validation_passed: event.validation_passed,
            thread_id: threadId,
          })
        }
        if (event.event === 'error') {
          assistantMsg = `Error: ${event.message}`
        }
      }

      setMessages(prev => [...prev, { role: 'assistant', content: assistantMsg }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="border border-gray-200 rounded-lg flex flex-col h-80">
      <div className="px-4 py-2 border-b border-gray-200 bg-gray-50 rounded-t-lg">
        <h4 className="text-sm font-semibold text-gray-700">Ask a follow-up question</h4>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {messages.length === 0 && (
          <p className="text-xs text-gray-400 text-center mt-4">
            Ask anything about this report — the agent will refine its analysis.
          </p>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-xs lg:max-w-md px-3 py-2 rounded-lg text-sm ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-800'
            }`}>
              {msg.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 px-3 py-2 rounded-lg text-sm text-gray-500 animate-pulse">
              Analysing…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSend} className="px-4 py-3 border-t border-gray-200 flex gap-2">
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="e.g. Why did the margin drop in Q3?"
          disabled={loading}
          className="flex-1 border border-gray-300 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={loading || !input.trim()}
          className="bg-blue-600 text-white px-3 py-1.5 rounded text-sm hover:bg-blue-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  )
}
