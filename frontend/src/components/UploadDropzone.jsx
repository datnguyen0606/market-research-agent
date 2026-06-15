import { useState, useRef } from 'react'
import { uploadDocument } from '../api/client'

const MAX_SIZE = 20 * 1024 * 1024

export default function UploadDropzone({ ticker, onIndexed }) {
  const [state, setState] = useState('idle') // idle | uploading | done | error
  const [message, setMessage] = useState('')
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  async function handleFile(file) {
    if (!file || !file.name.endsWith('.pdf')) {
      setState('error'); setMessage('Please select a PDF file.'); return
    }
    if (file.size > MAX_SIZE) {
      setState('error'); setMessage('File exceeds 20 MB limit.'); return
    }
    if (!ticker) {
      setState('error'); setMessage('Enter a ticker symbol first.'); return
    }
    setState('uploading'); setMessage('Uploading and indexing…')
    try {
      const result = await uploadDocument(ticker, file)
      setState('done')
      setMessage(`Indexed ${result.chunks_stored} sections across ${result.pages_processed} pages.`)
      onIndexed?.(result)
    } catch (err) {
      setState('error'); setMessage(err.message || 'Upload failed.')
    }
  }

  function onDrop(e) {
    e.preventDefault(); setDragging(false)
    handleFile(e.dataTransfer.files[0])
  }

  return (
    <div
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => inputRef.current?.click()}
      className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
        dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-gray-400'
      }`}
    >
      <input ref={inputRef} type="file" accept=".pdf" className="hidden" onChange={e => handleFile(e.target.files[0])} />
      {state === 'idle' && <p className="text-gray-500 text-sm">Drop a 10-K/10-Q PDF here or click to browse (max 20 MB)</p>}
      {state === 'uploading' && <p className="text-blue-600 text-sm">{message}</p>}
      {state === 'done' && <p className="text-green-700 text-sm">✓ {message}</p>}
      {state === 'error' && <p className="text-red-600 text-sm">✗ {message}</p>}
    </div>
  )
}
