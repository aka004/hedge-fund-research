import { useState, useEffect } from 'react'
import type { DashboardOverview, RunSummary } from '../../types/dashboard'
import { fetchDashboardOverview, fetchRuns } from '../../lib/dashboardApi'
import Pill from './shared/Pill'
import PortfolioTab from './PortfolioTab'
import FactorLabTab from './FactorLabTab'
import ValidationTab from './ValidationTab'
import RiskTab from './RiskTab'

const TABS = [
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'factors', label: 'Factor Lab' },
  { id: 'backtest', label: 'Validation' },
  { id: 'risk', label: 'Risk' },
] as const

type TabId = (typeof TABS)[number]['id']

export default function DashboardPage() {
  const [activeTab, setActiveTab] = useState<TabId>('portfolio')
  const [selectedRunId, setSelectedRunId] = useState<string | undefined>()
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        setLoading(true)
        const [runsRes, overviewRes] = await Promise.all([
          fetchRuns(),
          fetchDashboardOverview(selectedRunId),
        ])
        setRuns(runsRes.runs)
        setOverview(overviewRes)
        if (!selectedRunId && runsRes.runs.length > 0) {
          setSelectedRunId(runsRes.runs[0].run_id)
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load dashboard')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [selectedRunId])

  if (loading && !overview) {
    return <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">Loading...</div>
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-6 text-red-400">{error}</div>
      </div>
    )
  }

  const regimeColor = overview?.regime === 'bull' ? 'green' : overview?.regime === 'bear' ? 'red' : 'amber'

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans">
      {/* Header */}
      <div className="border-b border-slate-700 px-6 py-4 flex justify-between items-center">
        <div>
          <div className="text-sm font-bold tracking-[2px] uppercase text-cyan-500">AFML Research</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Portfolio Research Dashboard</div>
        </div>
        <div className="flex items-center gap-5">
          {runs.length > 1 && (
            <select
              value={selectedRunId ?? ''}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-300 text-xs rounded px-2 py-1.5 focus:outline-none focus:border-cyan-500"
            >
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.strategy_name} — {r.created_at.slice(0, 10)}
                </option>
              ))}
            </select>
          )}
          {overview && (
            <div className="text-right">
              <div className="text-xl font-bold font-mono">${overview.nav.toLocaleString()}</div>
              <div className={`text-xs font-semibold ${overview.total_pnl >= 0 ? 'text-green-500' : 'text-red-500'}`}>
                {overview.total_pnl >= 0 ? '+' : ''}${overview.total_pnl.toLocaleString()} ({overview.total_pnl_pct.toFixed(1)}%)
              </div>
            </div>
          )}
          {overview && <Pill color={regimeColor as 'green' | 'red' | 'amber'}>{overview.regime}</Pill>}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-700 px-6">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-5 py-3 text-[13px] font-semibold tracking-wide border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-cyan-500 text-cyan-500'
                : 'border-transparent text-slate-500 hover:text-slate-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="p-5 max-w-[1400px]">
        {activeTab === 'portfolio' && <PortfolioTab runId={selectedRunId} />}
        {activeTab === 'factors' && <FactorLabTab runId={selectedRunId} />}
        {activeTab === 'backtest' && <ValidationTab runId={selectedRunId} />}
        {activeTab === 'risk' && <RiskTab runId={selectedRunId} />}
      </div>
    </div>
  )
}
