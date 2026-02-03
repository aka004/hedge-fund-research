import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import FilterPanel from './FilterPanel'
import StockTable from './StockTable'
import { fetchScreener } from '../lib/api'
import type { Filter, SortConfig, StockSummary } from '../types/stock'

export default function ScreenerPage() {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const [filters, setFilters] = useState<Filter[]>([])
  const [sort, setSort] = useState<SortConfig>({ field: 'market_cap', direction: 'desc' })
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)
  const [stocks, setStocks] = useState<StockSummary[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showFilters, setShowFilters] = useState(true)

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
      
      setStocks(response.data)
      setTotal(response.total)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load stocks')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadStocks()
  }, [filters, sort, page, search])

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
          <div className="text-sm text-slate-400">
            {total.toLocaleString()} stocks found
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
