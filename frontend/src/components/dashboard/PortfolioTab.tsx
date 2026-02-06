import { useState, useEffect } from 'react'
import {
  ComposedChart, Line, Area, AreaChart, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import type { EquityPoint, Holding } from '../../types/dashboard'
import { fetchEquityCurve, fetchHoldings, fetchRiskMetrics } from '../../lib/dashboardApi'
import type { RiskMetrics } from '../../types/dashboard'
import Metric from './shared/Metric'
import Pill from './shared/Pill'
import SectionTitle from './shared/SectionTitle'
import ChartTooltip from './shared/ChartTooltip'

const SIGNAL_COLORS: Record<string, 'violet' | 'cyan' | 'green' | 'amber' | 'slate'> = {
  alpha: 'violet',
  momentum: 'cyan',
  value: 'green',
  social: 'amber',
}

interface PortfolioTabProps {
  runId?: string
}

export default function PortfolioTab({ runId }: PortfolioTabProps) {
  const [equityData, setEquityData] = useState<EquityPoint[]>([])
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [risk, setRisk] = useState<RiskMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [ec, h, r] = await Promise.all([
        fetchEquityCurve(runId),
        fetchHoldings(runId),
        fetchRiskMetrics(runId),
      ])
      setEquityData(ec.data)
      setHoldings(h.holdings)
      setRisk(r)
      setLoading(false)
    }
    load()
  }, [runId])

  if (loading) return <div className="text-center text-slate-400 py-12">Loading...</div>

  const latestEquity = equityData[equityData.length - 1]

  return (
    <div>
      {/* Top metrics */}
      <div className="grid grid-cols-5 gap-3 mb-5">
        <Metric label="NAV" value={latestEquity ? `$${latestEquity.equity.toLocaleString()}` : '-'} />
        <Metric label="Sharpe" value={risk ? risk.sharpe.toFixed(2) : '-'} color="text-cyan-500" />
        <Metric label="Max DD" value={risk ? `${risk.max_drawdown.toFixed(1)}%` : '-'} color="text-red-500" />
        <Metric label="Win Rate" value={risk ? `${(risk.win_rate * 100).toFixed(0)}%` : '-'} color="text-green-500" />
        <Metric label="Turnover" value={risk ? `${(risk.turnover * 100).toFixed(0)}%` : '-'} sub="monthly" />
      </div>

      {/* Equity Curve */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 mb-5">
        <SectionTitle tag="AFML Backtest Engine">Equity Curve</SectionTitle>
        <ResponsiveContainer width="100%" height={280}>
          <ComposedChart data={equityData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#475569' }} tickFormatter={(v: string) => v.slice(5)} interval={40} />
            <YAxis tick={{ fontSize: 10, fill: '#475569' }} domain={['auto', 'auto']} tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="benchmark_equity" fill="#47556910" stroke="#475569" strokeWidth={1} strokeDasharray="4 4" name="S&P 500" />
            <Line type="monotone" dataKey="equity" stroke="#06b6d4" strokeWidth={2} dot={false} name="Portfolio" />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Drawdown */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 mb-5">
        <SectionTitle>Drawdown</SectionTitle>
        <ResponsiveContainer width="100%" height={120}>
          <AreaChart data={equityData}>
            <XAxis dataKey="date" tick={false} />
            <YAxis tick={{ fontSize: 10, fill: '#475569' }} domain={['auto', 0]} tickFormatter={(v: number) => `${v}%`} />
            <Tooltip content={<ChartTooltip />} />
            <Area type="monotone" dataKey="drawdown" fill="#ef444420" stroke="#ef4444" strokeWidth={1.5} name="Drawdown %" />
          </AreaChart>
        </ResponsiveContainer>
      </div>

      {/* Holdings */}
      <HoldingsTable holdings={holdings} />
    </div>
  )
}

function HoldingsTable({ holdings }: { holdings: Holding[] }) {
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
      <SectionTitle tag={`${holdings.length} positions`}>Holdings</SectionTitle>
      <div className="overflow-x-auto">
        <table className="w-full text-[13px] border-collapse">
          <thead>
            <tr className="border-b border-slate-700">
              {['Ticker', 'Weight', 'P&L', 'Signal Source', 'Kelly', 'HRP Wt', 'Meta P(win)'].map((h) => (
                <th key={h} className="text-left px-3 py-2 text-[11px] text-slate-500 font-semibold uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {holdings.map((h) => (
              <tr key={h.ticker} className="border-b border-slate-700/20">
                <td className="px-3 py-2.5">
                  <span className="font-bold text-cyan-500">{h.ticker}</span>
                </td>
                <td className="px-3 py-2.5 font-mono">{(h.weight * 100).toFixed(1)}%</td>
                <td className={`px-3 py-2.5 font-mono ${(h.pnl_pct ?? 0) >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                  {(h.pnl_pct ?? 0) >= 0 ? '+' : ''}{(h.pnl_pct ?? 0).toFixed(1)}%
                </td>
                <td className="px-3 py-2.5">
                  <div className="flex gap-1 flex-wrap">
                    {h.signal_source.split('+').map((s) => (
                      <Pill key={s} color={SIGNAL_COLORS[s.trim()] ?? 'slate'}>{s.trim()}</Pill>
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2.5 font-mono text-slate-500">
                  {h.kelly_fraction > 0 ? h.kelly_fraction.toFixed(2) : '-'}
                </td>
                <td className="px-3 py-2.5 font-mono text-slate-500">
                  {h.hrp_weight > 0 ? `${(h.hrp_weight * 100).toFixed(1)}%` : '-'}
                </td>
                <td className="px-3 py-2.5">
                  <MetaProbBar value={h.meta_prob} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function MetaProbBar({ value }: { value: number | null }) {
  if (!value || value <= 0) return <span className="text-slate-600">-</span>
  const color = value > 0.7 ? 'bg-green-500' : value > 0.6 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-[60px] h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="font-mono text-xs text-slate-500">{(value * 100).toFixed(0)}%</span>
    </div>
  )
}
