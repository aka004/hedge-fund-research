import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell, ComposedChart, Line, ReferenceLine,
} from 'recharts'
import type {
  RiskMetrics, HRPWeightEntry, RegimePoint, KellySizingStep, Holding,
} from '../../types/dashboard'
import {
  fetchRiskMetrics, fetchHRPWeights, fetchRegimeHistory,
  fetchKellyPipeline, fetchHoldings,
} from '../../lib/dashboardApi'
import Metric from './shared/Metric'
import SectionTitle from './shared/SectionTitle'
import ChartTooltip from './shared/ChartTooltip'

const REGIME_COLORS: Record<string, string> = { bull: '#22c55e', bear: '#ef4444', neutral: '#f59e0b', volatile: '#f59e0b' }

interface RiskTabProps {
  runId?: string
}

export default function RiskTab({ runId }: RiskTabProps) {
  const [risk, setRisk] = useState<RiskMetrics | null>(null)
  const [hrpWeights, setHrpWeights] = useState<HRPWeightEntry[]>([])
  const [regimeData, setRegimeData] = useState<RegimePoint[]>([])
  const [holdings, setHoldings] = useState<Holding[]>([])
  const [kellySteps, setKellySteps] = useState<KellySizingStep[]>([])
  const [selectedTicker, setSelectedTicker] = useState<string>('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [r, hrp, reg, h] = await Promise.all([
        fetchRiskMetrics(runId),
        fetchHRPWeights(runId),
        fetchRegimeHistory(),
        fetchHoldings(runId),
      ])
      setRisk(r)
      setHrpWeights(hrp.weights)
      setRegimeData(reg.data)
      setHoldings(h.holdings)
      const firstTicker = h.holdings.find((x) => x.ticker !== 'CASH')?.ticker ?? ''
      setSelectedTicker(firstTicker)
      if (firstTicker) {
        const kelly = await fetchKellyPipeline(firstTicker, runId)
        setKellySteps(kelly.steps)
      }
      setLoading(false)
    }
    load()
  }, [runId])

  async function handleTickerChange(ticker: string) {
    setSelectedTicker(ticker)
    const kelly = await fetchKellyPipeline(ticker, runId)
    setKellySteps(kelly.steps)
  }

  if (loading) return <div className="text-center text-slate-400 py-12">Loading...</div>
  if (!risk) return null

  return (
    <div>
      <div className="grid grid-cols-5 gap-3 mb-5">
        <Metric label="Beta" value={risk.beta.toFixed(2)} sub="vs S&P 500" />
        <Metric label="Alpha (ann.)" value={`${(risk.alpha * 100).toFixed(1)}%`} color="text-green-500" />
        <Metric label="Sortino" value={risk.sortino.toFixed(2)} color="text-cyan-500" />
        <Metric label="Calmar" value={risk.calmar.toFixed(2)} />
        <Metric label="Profit Factor" value={risk.profit_factor.toFixed(2)} color="text-green-500" />
      </div>

      {/* Two-column grid */}
      <div className="grid grid-cols-2 gap-4 mb-5">
        <HRPChart weights={hrpWeights} />
        <RegimeChart data={regimeData} />
      </div>

      {/* Kelly Pipeline */}
      <KellyPipeline
        steps={kellySteps}
        selectedTicker={selectedTicker}
        holdings={holdings}
        onTickerChange={handleTickerChange}
      />
    </div>
  )
}

function HRPChart({ weights }: { weights: HRPWeightEntry[] }) {
  const sorted = [...weights].sort((a, b) => b.hrp_weight - a.hrp_weight)
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
      <SectionTitle tag="AFML Ch. 16">HRP Allocation Weights</SectionTitle>
      <div className="text-[11px] text-slate-500 mb-3">
        Hierarchical Risk Parity — inverse-variance weighting within correlation clusters.
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={sorted}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="ticker" tick={{ fontSize: 11, fill: '#64748b' }} />
          <YAxis tick={{ fontSize: 10, fill: '#475569' }} tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="hrp_weight" radius={[4, 4, 0, 0]} name="HRP Weight">
            {sorted.map((w, i) => (
              <Cell key={i} fill="#06b6d4" opacity={0.4 + (w.hrp_weight / (sorted[0]?.hrp_weight || 1)) * 0.6} />
            ))}
          </Bar>
          <Bar dataKey="actual_weight" radius={[4, 4, 0, 0]} name="Actual Weight" fill="#a78bfa" opacity={0.5} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function RegimeChart({ data }: { data: RegimePoint[] }) {
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
      <SectionTitle tag="AFML Ch. 8">Regime Detection</SectionTitle>
      <div className="text-[11px] text-slate-500 mb-3">
        CUSUM filter detects structural breaks. Current regime informs position sizing.
      </div>
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#64748b' }} tickFormatter={(v: string) => v.slice(5)} />
          <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#475569' }} />
          <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#475569' }} />
          <Tooltip content={<ChartTooltip />} />
          <Bar yAxisId="left" dataKey="distance_pct" name="Distance %" radius={[4, 4, 0, 0]}>
            {data.map((d, i) => (
              <Cell key={i} fill={REGIME_COLORS[d.regime] ?? '#f59e0b'} opacity={0.6} />
            ))}
          </Bar>
          <Line yAxisId="right" type="monotone" dataKey="cusum_value" stroke="#06b6d4" strokeWidth={2} dot={{ r: 4, fill: '#06b6d4' }} name="CUSUM" />
          <ReferenceLine yAxisId="right" y={1.5} stroke="#ef4444" strokeDasharray="4 4" />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function KellyPipeline({
  steps, selectedTicker, holdings, onTickerChange,
}: {
  steps: KellySizingStep[]
  selectedTicker: string
  holdings: Holding[]
  onTickerChange: (t: string) => void
}) {
  const tickers = holdings.filter((h) => h.ticker !== 'CASH').map((h) => h.ticker)

  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
      <div className="flex items-center justify-between mb-4">
        <SectionTitle tag="AFML Ch. 10">Kelly Sizing Pipeline</SectionTitle>
        <select
          value={selectedTicker}
          onChange={(e) => onTickerChange(e.target.value)}
          className="bg-slate-800 border border-slate-700 text-slate-300 text-xs rounded px-2 py-1 focus:outline-none focus:border-cyan-500"
        >
          {tickers.map((t) => (
            <option key={t} value={t}>{t}</option>
          ))}
        </select>
      </div>
      <div className="text-[11px] text-slate-500 mb-4 leading-relaxed">
        {'Meta-labeling probability \u2192 Kelly criterion \u2192 Half-Kelly (safety) \u2192 HRP cluster weight \u2192 Budget constraint \u2192 Final position.'}
      </div>
      <div className="grid grid-cols-6 gap-2 text-center">
        {steps.map((s, i) => (
          <div
            key={i}
            className={`px-2 py-2.5 rounded-md border ${
              i === steps.length - 1
                ? 'bg-cyan-500/10 border-cyan-500/30'
                : 'bg-slate-950 border-slate-700'
            }`}
          >
            <div className="text-[10px] text-slate-500 mb-1.5">{s.step}</div>
            <div className={`font-mono text-[13px] font-semibold ${i === steps.length - 1 ? 'text-cyan-500' : 'text-slate-200'}`}>
              {formatStepValue(s.value, s.step)}
            </div>
            <div className="text-[10px] text-slate-600 mt-0.5">{s.ticker}</div>
          </div>
        ))}
      </div>
    </div>
  )
}

function formatStepValue(value: number, step: string): string {
  if (step.toLowerCase().includes('prob') || step.toLowerCase().includes('final') || step.toLowerCase().includes('%')) {
    return `${(value * 100).toFixed(0)}%`
  }
  return value.toFixed(2)
}
