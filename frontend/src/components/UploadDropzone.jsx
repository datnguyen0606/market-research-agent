import { useState, useRef } from 'react'
import { uploadDocument } from '../api/client'

const MAX_SIZE = 20 * 1024 * 1024
const ACCEPTED_EXT = ['.pdf', '.docx']
const ACCEPTED_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
]

function isAccepted(file) {
  if (ACCEPTED_TYPES.includes(file.type)) return true
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  return ACCEPTED_EXT.includes(ext)
}

export default function UploadDropzone() {
  const [uploads, setUploads] = useState([])  // [{filename, status, message}]
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)

  async function handleFile(file) {
    if (!file) return
    if (!isAccepted(file)) {
      setUploads(prev => [...prev, { filename: file.name, status: 'error', message: 'Only PDF and DOCX files are supported.' }])
      return
    }
    if (file.size > MAX_SIZE) {
      setUploads(prev => [...prev, { filename: file.name, status: 'error', message: 'File exceeds 20 MB limit.' }])
      return
    }

    setUploads(prev => [...prev, { filename: file.name, status: 'uploading', message: 'Uploading and indexing…' }])

    try {
      const result = await uploadDocument(file)
      setUploads(prev => prev.map(u =>
        u.filename === file.name && u.status === 'uploading'
          ? { filename: file.name, status: 'done', message: `Indexed ${result.chunks_stored} sections across ${result.pages_processed} pages.` }
          : u
      ))
    } catch (err) {
      setUploads(prev => prev.map(u =>
        u.filename === file.name && u.status === 'uploading'
          ? { filename: file.name, status: 'error', message: err.message || 'Upload failed.' }
          : u
      ))
    }
  }

  function onDrop(e) {
    e.preventDefault(); setDragging(false)
    Array.from(e.dataTransfer.files).forEach(handleFile)
  }

  function onFileChange(e) {
    Array.from(e.target.files).forEach(handleFile)
    e.target.value = ''  // allow re-uploading same file
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
          dragging ? 'border-blue-400 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx"
          multiple
          className="hidden"
          onChange={onFileChange}
        />
        <p className="text-gray-500 text-sm">
          Drop PDF or DOCX files here, or <span className="text-blue-600 font-medium">click to browse</span>
        </p>
        <p className="text-gray-400 text-xs mt-1">Max 20 MB per file · Multiple files supported</p>
      </div>

      {uploads.length > 0 && (
        <ul className="space-y-2">
          {uploads.map((u, i) => (
            <li key={i} className={`flex items-start gap-2 text-sm rounded-lg px-3 py-2 ${
              u.status === 'done' ? 'bg-green-50 text-green-800' :
              u.status === 'error' ? 'bg-red-50 text-red-700' :
              'bg-blue-50 text-blue-700'
            }`}>
              <span className="font-medium shrink-0">
                {u.status === 'done' ? '✓' : u.status === 'error' ? '✗' : '…'}
              </span>
              <span><span className="font-medium">{u.filename}</span> — {u.message}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
