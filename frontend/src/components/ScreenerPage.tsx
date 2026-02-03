import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

export default function ScreenerPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-2xl font-bold text-blue-500">HF</div>
            <div className="text-xl font-semibold">Stock Screener</div>
          </div>
          <div className="text-sm text-slate-400">
            v1.0.0 - Hedge Fund Research
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        <div className="mb-6">
          <input
            type="text"
            placeholder="Search by ticker or company name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full max-w-md px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg p-8 text-center">
          <div className="text-6xl mb-4">🚀</div>
          <h2 className="text-2xl font-bold mb-2">
            Stock Screener Under Construction
          </h2>
          <p className="text-slate-400 mb-6">
            Backend API and frontend components are being built by the multi-agent workflow.
          </p>
          <div className="space-y-2 text-left max-w-md mx-auto">
            <div className="flex items-center gap-2 text-sm">
              <span className="text-green-500">✓</span>
              <span>Database schema migrated</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-green-500">✓</span>
              <span>Backend structure created</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-green-500">✓</span>
              <span>Frontend scaffold ready</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-yellow-500">⟳</span>
              <span>API endpoints (in progress)</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-yellow-500">⟳</span>
              <span>Filter panel & table (in progress)</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
