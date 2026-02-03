import { useParams, useNavigate } from 'react-router-dom'

export default function StockDetailPage() {
  const { ticker } = useParams<{ ticker: string }>()
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="flex items-center gap-6">
          <button
            onClick={() => navigate('/screener')}
            className="text-blue-500 hover:text-blue-400"
          >
            ← Back to Screener
          </button>
          <div className="text-2xl font-bold">{ticker}</div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-8 text-center">
          <div className="text-6xl mb-4">📊</div>
          <h2 className="text-2xl font-bold mb-2">
            Stock Detail Page
          </h2>
          <p className="text-slate-400">
            Detailed view for {ticker} coming soon...
          </p>
        </div>
      </main>
    </div>
  )
}
