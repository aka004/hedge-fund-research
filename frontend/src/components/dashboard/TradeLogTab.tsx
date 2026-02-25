import { useState, useEffect, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { TradeLogEntry, TradeLogSummary } from '../../types/dashboard'
import { fetchTradeLog } from '../../lib/dashboardApi'
import Metric from './shared/Metric'
import Pill from './shared/Pill'
import SectionTitle from './shared/SectionTitle'
import ChartTooltip from './shared/ChartTooltip'

const EXIT_COLORS: Record<string, string> = {
  profit_target: '#22c55e',
  stop_loss: '#ef4444',
  timeout: '#f59e0b',
  rebalance_out: '#64748b',
}

const EXIT_PILL_COLORS: Record<string, 'green' | 'red' | 'amber' | 'slate'> = {
  profit_target: 'green',
  stop_loss: 'red',
  timeout: 'amber',
  rebalance_out: 'slate',
}

type SortKey = keyof TradeLogEntry
type SortDir = 'asc' | 'desc'

const PAGE_SIZE = 20

interface TradeLogTabProps {
  runId?: string
}

export default function TradeLogTab({ runId }: TradeLogTabProps) {
  const [trades, setTrades] = useState<TradeLogEntry[]>([])
  const [summary, setSummary] = useState<TradeLogSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('exit_date')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [page, setPage] = useState(0)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        setError(null)
        const res = await fetchTradeLog(runId)
        setTrades(res.trades)
        setSummary(res.summary)
        setPage(0)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load trade log')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [runId])

  const sorted = useMemo(() => {
    const copy = [...trades]
    copy.sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      const as = String(av)
      const bs = String(bv)
      return sortDir === 'asc' ? as.localeCompare(bs) : bs.localeCompare(as)
    })
    return copy
  }, [trades, sortKey, sortDir])

  const totalPages = Math.ceil(sorted.length / PAGE_SIZE)
  const paged = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
    setPage(0)
  }

  if (loading) return <div className="text-center text-slate-400 py-12">Loading...</div>
  if (error) return <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-red-400">{error}</div>

  const exitData = summary
    ? Object.entries(summary.exit_breakdown).map(([reason, pct]) => ({
        reason: reason.replace(/_/g, ' '),
        pct: +(pct * 100).toFixed(1),
        fill: EXIT_COLORS[reason] ?? '#64748b',
      }))
    : []

  return (
    <div>
      {/* Summary metrics */}
      {summary && (
        <div className="grid grid-cols-4 gap-3 mb-5">
          <Metric label="Total Trades" value={summary.total_trades.toString()} />
          <Metric label="Win Rate" value={`${(summary.win_rate * 100).toFixed(0)}%`} color="text-green-500" />
          <Metric label="Profit Factor" value={summary.profit_factor.toFixed(2)} color="text-cyan-500" />
          <Metric label="Avg Holding" value={`${summary.avg_holding_days.toFixed(1)}d`} />
        </div>
      )}

      {/* Exit Breakdown Chart */}
      {exitData.length > 0 && (
        <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 mb-5">
          <SectionTitle tag="exit reasons">Exit Breakdown</SectionTitle>
          <ResponsiveContainer width="100%" height={120}>
            <BarChart data={exitData} layout="vertical" margin={{ left: 80 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: '#475569' }} tickFormatter={(v: number) => `${v}%`} />
              <YAxis type="category" dataKey="reason" tick={{ fontSize: 11, fill: '#94a3b8' }} width={80} />
              <Tooltip content={<ChartTooltip />} />
              <Bar dataKey="pct" name="%" radius={[0, 4, 4, 0]} barSize={18}>
                {exitData.map((d, i) => (
                  <Cell key={i} fill={d.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Trade table */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
        <SectionTitle tag={`${trades.length} round-trips`}>Trade Log</SectionTitle>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px] border-collapse">
            <thead>
              <tr className="border-b border-slate-700">
                {COLUMNS.map((col) => (
                  <th
                    key={col.key}
                    onClick={() => toggleSort(col.key)}
                    className="text-left px-3 py-2 text-[11px] text-slate-500 font-semibold uppercase tracking-wide cursor-pointer hover:text-slate-300 select-none"
                  >
                    {col.label}
                    {sortKey === col.key && <span className="ml-1">{sortDir === 'asc' ? '↑' : '↓'}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {paged.map((t, i) => (
                <tr key={i} className="border-b border-slate-700/20 hover:bg-slate-800/40">
                  <td className="px-3 py-2.5">
                    <span className="font-bold text-cyan-500">{t.symbol}</span>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-slate-400">{t.entry_date.slice(0, 10)}</td>
                  <td className="px-3 py-2.5 font-mono text-slate-400">{t.exit_date.slice(0, 10)}</td>
                  <td className="px-3 py-2.5">
                    <Pill color={EXIT_PILL_COLORS[t.entry_reason] ?? 'slate'}>{t.entry_reason.replace(/_/g, ' ')}</Pill>
                  </td>
                  <td className="px-3 py-2.5">
                    <Pill color={EXIT_PILL_COLORS[t.exit_reason] ?? 'slate'}>{t.exit_reason.replace(/_/g, ' ')}</Pill>
                  </td>
                  <td className="px-3 py-2.5 font-mono text-slate-400">{t.holding_days}</td>
                  <td className={`px-3 py-2.5 font-mono font-semibold ${t.return_pct >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {t.return_pct >= 0 ? '+' : ''}{(t.return_pct * 100).toFixed(1)}%
                  </td>
                  <td className={`px-3 py-2.5 font-mono font-semibold ${t.pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                    {t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(0)}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-green-500/70">{(t.max_favorable * 100).toFixed(1)}%</td>
                  <td className="px-3 py-2.5 font-mono text-red-500/70">{(t.max_adverse * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-3 border-t border-slate-700">
            <span className="text-xs text-slate-500">
              Page {page + 1} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="px-3 py-1 text-xs rounded border border-slate-700 text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Prev
              </button>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="px-3 py-1 text-xs rounded border border-slate-700 text-slate-400 hover:text-slate-200 disabled:opacity-30 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'symbol', label: 'Symbol' },
  { key: 'entry_date', label: 'Entry' },
  { key: 'exit_date', label: 'Exit' },
  { key: 'entry_reason', label: 'Entry Reason' },
  { key: 'exit_reason', label: 'Exit Reason' },
  { key: 'holding_days', label: 'Days' },
  { key: 'return_pct', label: 'Return %' },
  { key: 'pnl', label: 'PnL' },
  { key: 'max_favorable', label: 'MFE' },
  { key: 'max_adverse', label: 'MAE' },
]
