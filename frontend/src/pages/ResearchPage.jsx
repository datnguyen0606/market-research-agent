import { useState } from 'react'
import { useAuth } from '../auth/AuthContext'
import ChatPanel from '../components/ChatPanel'
import UploadDropzone from '../components/UploadDropzone'

export default function ResearchPage() {
  const { username, logout } = useAuth()
  const [activeTab, setActiveTab] = useState('query')

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between shrink-0">
        <h1 className="text-lg font-bold text-gray-900">Market Research Agent</h1>
        <div className="flex items-center gap-4">
          <span className="text-sm text-gray-500">{username}</span>
          <button onClick={logout} className="text-sm text-gray-500 hover:text-gray-700">Sign out</button>
        </div>
      </header>

      <div className="border-b border-gray-200 bg-white px-6 shrink-0">
        <nav className="flex gap-6">
          {[
            { id: 'query', label: 'AI Query' },
            { id: 'upload', label: 'Document Upload' },
          ].map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`py-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
                activeTab === tab.id
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      <main className="flex-1 flex flex-col overflow-hidden">
        {activeTab === 'query' && <ChatPanel />}
        {activeTab === 'upload' && (
          <div className="max-w-2xl mx-auto w-full px-6 py-8 space-y-4">
            <div>
              <h2 className="text-base font-semibold text-gray-800">Upload Documents</h2>
              <p className="text-sm text-gray-500 mt-1">
                Upload any PDF or DOCX file — annual reports, earnings releases, research papers, news articles.
                The AI will use these documents when answering your questions.
              </p>
            </div>
            <UploadDropzone />
          </div>
        )}
      </main>
    </div>
  )
}
