import { useState } from 'react'
import type { StockSummary, SortConfig } from '../types/stock'
import { formatCurrency, formatPercent, formatNumber, formatVolume, getPriceChangeColor } from '../lib/formatters'

interface StockTableProps {
  stocks: StockSummary[]
  onSort: (sort: SortConfig) => void
  onRowClick: (ticker: string) => void
}

export default function StockTable({ stocks, onSort, onRowClick }: StockTableProps) {
  const [sortField, setSortField] = useState('market_cap')
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc')

  const handleHeaderClick = (field: string) => {
    const newDirection = sortField === field && sortDirection === 'desc' ? 'asc' : 'desc'
    setSortField(field)
    setSortDirection(newDirection)
    onSort({ field, direction: newDirection })
  }

  const SortIcon = ({ field }: { field: string }) => {
    if (sortField !== field) return null
    return sortDirection === 'desc' ? ' ↓' : ' ↑'
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-slate-800 border-b border-slate-700">
          <tr>
            <th
              onClick={() => handleHeaderClick('ticker')}
              className="px-4 py-3 text-left text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Ticker<SortIcon field="ticker" />
            </th>
            <th
              onClick={() => handleHeaderClick('price')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Price<SortIcon field="price" />
            </th>
            <th
              onClick={() => handleHeaderClick('price_change_pct')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Change %<SortIcon field="price_change_pct" />
            </th>
            <th
              onClick={() => handleHeaderClick('market_cap')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Market Cap<SortIcon field="market_cap" />
            </th>
            <th
              onClick={() => handleHeaderClick('volume')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Volume<SortIcon field="volume" />
            </th>
            <th
              onClick={() => handleHeaderClick('pe_ratio')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              P/E<SortIcon field="pe_ratio" />
            </th>
            <th
              onClick={() => handleHeaderClick('roe')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              ROE<SortIcon field="roe" />
            </th>
            <th
              onClick={() => handleHeaderClick('gross_margin')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Gross Margin<SortIcon field="gross_margin" />
            </th>
            <th
              onClick={() => handleHeaderClick('revenue_growth_yoy')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              Rev Growth<SortIcon field="revenue_growth_yoy" />
            </th>
            <th
              onClick={() => handleHeaderClick('rsi_14')}
              className="px-4 py-3 text-right text-sm font-medium cursor-pointer hover:bg-slate-700"
            >
              RSI<SortIcon field="rsi_14" />
            </th>
          </tr>
        </thead>
        <tbody>
          {stocks.map((stock) => (
            <tr
              key={stock.ticker}
              onClick={() => onRowClick(stock.ticker)}
              className="border-b border-slate-700 hover:bg-slate-800 cursor-pointer"
            >
              <td className="px-4 py-3">
                <div className="font-medium">{stock.ticker}</div>
                <div className="text-xs text-slate-400 truncate max-w-xs">
                  {stock.name}
                </div>
              </td>
              <td className="px-4 py-3 text-right font-mono">
                {stock.price ? `$${stock.price.toFixed(2)}` : '-'}
              </td>
              <td className={`px-4 py-3 text-right font-mono ${getPriceChangeColor(stock.price_change_pct)}`}>
                {stock.price_change_pct !== undefined && stock.price_change_pct !== null
                  ? `${stock.price_change_pct >= 0 ? '+' : ''}${stock.price_change_pct.toFixed(2)}%`
                  : '-'}
              </td>
              <td className="px-4 py-3 text-right">{formatCurrency(stock.market_cap)}</td>
              <td className="px-4 py-3 text-right">{formatVolume(stock.volume)}</td>
              <td className="px-4 py-3 text-right">{formatNumber(stock.pe_ratio)}</td>
              <td className="px-4 py-3 text-right">{formatPercent(stock.roe)}</td>
              <td className="px-4 py-3 text-right">{formatPercent(stock.gross_margin)}</td>
              <td className="px-4 py-3 text-right">{formatPercent(stock.revenue_growth_yoy)}</td>
              <td className="px-4 py-3 text-right">{formatNumber(stock.rsi_14)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      
      {stocks.length === 0 && (
        <div className="text-center py-12 text-slate-400">
          No stocks match your filters
        </div>
      )}
    </div>
  )
}
