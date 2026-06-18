import { useState, useRef, useEffect } from 'react'
import { marked } from 'marked'
import { streamResearch, streamChat } from '../api/client'

marked.setOptions({ breaks: true, gfm: true })

function SourcesList({ sources }) {
  const [open, setOpen] = useState(false)
  if (!sources?.length) return null
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(o => !o)}
        className="text-xs text-blue-600 hover:underline"
      >
        {open ? 'Hide' : 'Show'} {sources.length} source{sources.length !== 1 ? 's' : ''}
      </button>
      {open && (
        <ul className="mt-1 space-y-1">
          {sources.map((s, i) => (
            <li key={i} className="text-xs text-gray-500">
              {s.url
                ? <a href={s.url} target="_blank" rel="noreferrer" className="text-blue-500 hover:underline">{s.title || s.url}</a>
                : <span>{s.title || 'Uploaded document'}</span>
              }
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Message({ msg }) {
  if (msg.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] px-4 py-2.5 rounded-2xl rounded-tr-sm bg-blue-600 text-white text-sm">
          {msg.content}
        </div>
      </div>
    )
  }

  return (
    <div className="flex justify-start">
      <div className="max-w-[85%]">
        <div
          className="px-4 py-2.5 rounded-2xl rounded-tl-sm bg-white border border-gray-200 text-sm text-gray-800 prose prose-sm max-w-none"
          dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) }}
        />
        <SourcesList sources={msg.sources} />
        {msg.grounding_passed === false && (
          <p className="text-xs text-amber-600 mt-1">⚠ Some claims may not be fully grounded in sources.</p>
        )}
      </div>
    </div>
  )
}

export default function ChatPanel() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [currentNode, setCurrentNode] = useState(null)
  const [threadId, setThreadId] = useState(null)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const NODE_LABELS = {
    router: 'Planning search strategy…',
    retrieval: 'Searching documents and web…',
    analyst: 'Synthesising answer…',
    grounding: 'Verifying sources…',
  }

  async function handleSend(e) {
    e.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    setInput('')
    setLoading(true)
    setCurrentNode(null)
    setMessages(prev => [...prev, { role: 'user', content: text }])

    try {
      const stream = threadId
        ? streamChat(threadId, text)
        : streamResearch({ query: text })

      let answer = ''
      let sources = []
      let groundingPassed = true

      for await (const event of stream) {
        if (event.event === 'node_complete') {
          setCurrentNode(event.node)
        }
        if (event.event === 'done') {
          if (!threadId && event.thread_id) setThreadId(event.thread_id)
          answer = event.answer || ''
          sources = event.sources || []
          groundingPassed = event.grounding_passed !== false
        }
        if (event.event === 'error') {
          answer = `Error: ${event.message}`
        }
      }

      setMessages(prev => [...prev, {
        role: 'assistant',
        content: answer || 'No answer returned.',
        sources,
        grounding_passed: groundingPassed,
      }])
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: `Error: ${err.message}`,
        sources: [],
      }])
    } finally {
      setLoading(false)
      setCurrentNode(null)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center text-gray-400 select-none">
            <p className="text-lg font-medium mb-2">Ask anything about financial data</p>
            <p className="text-sm max-w-md">
              Try: "Give me the top 5 companies with the best margins in the uploaded reports"
              or "What are the main risks mentioned in the documents?"
            </p>
          </div>
        )}
        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {loading && (
          <div className="flex justify-start">
            <div className="px-4 py-2.5 rounded-2xl rounded-tl-sm bg-white border border-gray-200 text-sm text-gray-400 animate-pulse">
              {NODE_LABELS[currentNode] || 'Thinking…'}
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-gray-200 bg-white px-4 py-4 shrink-0">
        <form onSubmit={handleSend} className="flex gap-3 max-w-3xl mx-auto">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask a question about your documents or financial markets…"
            disabled={loading}
            className="flex-1 border border-gray-300 rounded-xl px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-blue-600 text-white px-5 py-2.5 rounded-xl text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
          >
            {loading ? '…' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  )
}
