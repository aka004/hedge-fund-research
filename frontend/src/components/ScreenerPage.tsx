import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import FilterPanel from './FilterPanel'
import StockTable from './StockTable'
import { fetchScreener } from '../lib/api'
import { getWatchlist } from '../lib/watchlist'
import { exportStocksToCSV } from '../lib/csvExport'
import type { Filter, SortConfig, StockSummary } from '../types/stock'

type FilterPreset = 'value' | 'growth' | 'momentum' | 'oversold' | null

export default function ScreenerPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Filter[]>([])
  const [sort, setSort] = useState<SortConfig>({ field: 'market_cap', direction: 'desc' })
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [stocks, setStocks] = useState<StockSummary[]>([])
  const [allStocks, setAllStocks] = useState<StockSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(true)
  const [showWatchlistOnly, setShowWatchlistOnly] = useState(false)
  const [activePreset, setActivePreset] = useState<FilterPreset>(null)

  const loadStocks = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetchScreener({
        filters,
        sort,
        page,
        page_size: pageSize,
        search: search || undefined,
      })
      
      setAllStocks(response.data)
      
      // Apply watchlist filter if enabled
      let filteredStocks = response.data
      if (showWatchlistOnly) {
        const watchlist = getWatchlist()
        filteredStocks = response.data.filter(stock => 
          watchlist.includes(stock.ticker.toUpperCase())
        )
      }
      
      setStocks(filteredStocks)
      setTotal(showWatchlistOnly ? filteredStocks.length : response.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load stocks')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStocks()
  }, [filters, sort, page, search, showWatchlistOnly])

  const applyPreset = (preset: FilterPreset) => {
    setActivePreset(preset)
    setPage(1)
    
    let newFilters: Filter[] = []
    
    switch (preset) {
      case 'value':
        newFilters = [
          { field: 'pe_ratio', operator: 'between', value: [0, 15] },
          { field: 'dividend_yield', operator: 'gte', value: 2 },
        ]
        break
      case 'growth':
        newFilters = [
          { field: 'revenue_growth_yoy', operator: 'gte', value: 15 },
          { field: 'earnings_growth_yoy', operator: 'gte', value: 10 },
        ]
        break
      case 'momentum':
        newFilters = [
          { field: 'rsi_14', operator: 'between', value: [40, 70] },
        ]
        break
      case 'oversold':
        newFilters = [
          { field: 'rsi_14', operator: 'lt', value: 30 },
        ]
        break
    }
    
    setFilters(newFilters)
  }

  const clearPreset = () => {
    setActivePreset(null)
    setFilters([])
    setPage(1)
  }

  const totalPages = Math.ceil(total / pageSize)

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="text-2xl font-bold text-blue-500">HF</div>
            <div className="text-xl font-semibold">Stock Screener</div>
          </div>
          <div className="flex items-center gap-4">
            <Link
              to="/dashboard"
              className="px-3 py-1.5 text-sm font-medium text-cyan-400 border border-cyan-800 rounded-lg hover:bg-cyan-900/20 transition-colors"
            >
              Dashboard
            </Link>
            <span className="text-sm text-slate-400">
              {total.toLocaleString()} stocks found
            </span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
          {/* Sidebar - Filters */}
          {showFilters && (
            <div className="lg:col-span-1">
              <FilterPanel onFiltersChange={(newFilters) => {
                setFilters(newFilters)
                setPage(1) // Reset to first page on filter change
              }} />
            </div>
          )}

          {/* Main Content Area */}
          <div className={showFilters ? 'lg:col-span-3' : 'lg:col-span-4'}>
            {/* Filter Presets */}
            <div className="mb-4 space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-slate-400">Quick Filters:</span>
                <button
                  onClick={() => applyPreset('value')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activePreset === 'value'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-800 border border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  💰 Value
                </button>
                <button
                  onClick={() => applyPreset('growth')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activePreset === 'growth'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-800 border border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  📈 Growth
                </button>
                <button
                  onClick={() => applyPreset('momentum')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activePreset === 'momentum'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-800 border border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  🚀 Momentum
                </button>
                <button
                  onClick={() => applyPreset('oversold')}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    activePreset === 'oversold'
                      ? 'bg-blue-600 text-white'
                      : 'bg-slate-800 border border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  🔻 Oversold
                </button>
                {activePreset && (
                  <button
                    onClick={clearPreset}
                    className="px-4 py-2 bg-red-900/20 border border-red-900 text-red-400 rounded-lg text-sm font-medium hover:bg-red-900/30"
                  >
                    Clear Preset
                  </button>
                )}
              </div>
              {activePreset && (
                <div className="text-xs text-slate-400 px-2">
                  {activePreset === 'value' && '✓ P/E < 15, Dividend Yield > 2%'}
                  {activePreset === 'growth' && '✓ Revenue Growth > 15%, Earnings Growth > 10%'}
                  {activePreset === 'momentum' && '✓ RSI between 40-70'}
                  {activePreset === 'oversold' && '✓ RSI < 30'}
                </div>
              )}
            </div>

            {/* Search */}
            <div className="mb-4 flex gap-4">
              <input
                type="text"
                placeholder="Search by ticker or company name..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value)
                  setPage(1)
                }}
                className="flex-1 px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => setShowWatchlistOnly(!showWatchlistOnly)}
                className={`px-4 py-2 rounded-lg font-medium transition-colors ${
                  showWatchlistOnly
                    ? 'bg-yellow-600 text-white'
                    : 'bg-slate-800 border border-slate-700 hover:bg-slate-700'
                }`}
              >
                ★ {showWatchlistOnly ? 'All Stocks' : 'Watchlist'}
              </button>
              <button
                onClick={() => exportStocksToCSV(stocks)}
                disabled={stocks.length === 0}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 border border-blue-500 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                title={stocks.length === 0 ? 'No stocks to export' : `Export ${stocks.length} stocks to CSV`}
              >
                📥 Export CSV
              </button>
              <button
                onClick={() => setShowFilters(!showFilters)}
                className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700"
              >
                {showFilters ? 'Hide' : 'Show'} Filters
              </button>
            </div>

            {/* Error */}
            {error && (
              <div className="mb-4 p-4 bg-red-900/20 border border-red-900 rounded-lg text-red-400">
                {error}
              </div>
            )}

            {/* Table */}
            <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
              {loading ? (
                <div className="text-center py-12 text-slate-400">
                  Loading...
                </div>
              ) : (
                <StockTable
                  stocks={stocks}
                  onSort={(newSort) => setSort(newSort)}
                  onRowClick={(ticker) => navigate(`/stock/${ticker}`)}
                />
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-4 flex items-center justify-between">
                <div className="text-sm text-slate-400">
                  Page {page} of {totalPages}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage(Math.max(1, page - 1))}
                    disabled={page === 1}
                    className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage(Math.min(totalPages, page + 1))}
                    disabled={page === totalPages}
                    className="px-4 py-2 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
