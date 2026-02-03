import { useState } from 'react'
import type { Filter } from '../types/stock'

interface FilterPanelProps {
  onFiltersChange: (filters: Filter[]) => void
}

export default function FilterPanel({ onFiltersChange }: FilterPanelProps) {
  const [sector, setSector] = useState<string[]>([])
  const [peMin, setPeMin] = useState('')
  const [peMax, setPeMax] = useState('')
  const [marketCapMin, setMarketCapMin] = useState('')
  const [rsiMin, setRsiMin] = useState('')
  const [rsiMax, setRsiMax] = useState('')

  const sectors = [
    'Technology',
    'Healthcare',
    'Financial Services',
    'Consumer Cyclical',
    'Industrials',
    'Communication Services',
    'Consumer Defensive',
    'Energy',
    'Utilities',
    'Real Estate',
    'Basic Materials',
  ]

  const handleApply = () => {
    const filters: Filter[] = []

    if (sector.length > 0) {
      filters.push({
        field: 'sector',
        operator: 'in',
        value: sector,
      })
    }

    if (peMin || peMax) {
      filters.push({
        field: 'pe_ratio',
        operator: 'between',
        value: [parseFloat(peMin) || 0, parseFloat(peMax) || 1000],
      })
    }

    if (marketCapMin) {
      filters.push({
        field: 'market_cap',
        operator: 'gte',
        value: parseFloat(marketCapMin) * 1e9, // Convert B to raw
      })
    }

    if (rsiMin || rsiMax) {
      filters.push({
        field: 'rsi_14',
        operator: 'between',
        value: [parseFloat(rsiMin) || 0, parseFloat(rsiMax) || 100],
      })
    }

    onFiltersChange(filters)
  }

  const handleClear = () => {
    setSector([])
    setPeMin('')
    setPeMax('')
    setMarketCapMin('')
    setRsiMin('')
    setRsiMax('')
    onFiltersChange([])
  }

  const toggleSector = (s: string) => {
    setSector((prev) =>
      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
    )
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold">Filters</h3>
        <div className="flex gap-2">
          <button
            onClick={handleClear}
            className="px-3 py-1 text-sm bg-slate-700 hover:bg-slate-600 rounded"
          >
            Clear
          </button>
          <button
            onClick={handleApply}
            className="px-3 py-1 text-sm bg-blue-600 hover:bg-blue-500 rounded"
          >
            Apply
          </button>
        </div>
      </div>

      {/* Sector */}
      <div>
        <label className="block text-sm font-medium mb-2">Sector</label>
        <div className="grid grid-cols-2 gap-2">
          {sectors.map((s) => (
            <label key={s} className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={sector.includes(s)}
                onChange={() => toggleSector(s)}
                className="rounded"
              />
              <span>{s}</span>
            </label>
          ))}
        </div>
      </div>

      {/* P/E Ratio */}
      <div>
        <label className="block text-sm font-medium mb-2">P/E Ratio</label>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="number"
            placeholder="Min"
            value={peMin}
            onChange={(e) => setPeMin(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="number"
            placeholder="Max"
            value={peMax}
            onChange={(e) => setPeMax(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>

      {/* Market Cap */}
      <div>
        <label className="block text-sm font-medium mb-2">Min Market Cap (B)</label>
        <input
          type="number"
          placeholder="e.g. 10"
          value={marketCapMin}
          onChange={(e) => setMarketCapMin(e.target.value)}
          className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>

      {/* RSI */}
      <div>
        <label className="block text-sm font-medium mb-2">RSI (14)</label>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="number"
            placeholder="Min (e.g. 30)"
            value={rsiMin}
            onChange={(e) => setRsiMin(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="number"
            placeholder="Max (e.g. 70)"
            value={rsiMax}
            onChange={(e) => setRsiMax(e.target.value)}
            className="px-3 py-2 bg-slate-700 border border-slate-600 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>
      </div>
    </div>
  )
}
