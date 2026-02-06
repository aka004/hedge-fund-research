import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import type { DiscoveredFactor, FeatureImportance } from '../../types/dashboard'
import { fetchFactors, fetchFeatureImportance } from '../../lib/dashboardApi'
import Metric from './shared/Metric'
import Pill from './shared/Pill'
import SectionTitle from './shared/SectionTitle'
import MockBadge from './shared/MockBadge'
import ChartTooltip from './shared/ChartTooltip'

const IMPORTANCE_COLORS = ['#06b6d4', '#22c55e', '#f59e0b', '#a78bfa', '#3b82f6', '#f472b6', '#475569']

interface FactorLabTabProps {
  runId?: string
}

export default function FactorLabTab({ runId }: FactorLabTabProps) {
  const [factors, setFactors] = useState<DiscoveredFactor[]>([])
  const [features, setFeatures] = useState<FeatureImportance[]>([])
  const [selectedFactor, setSelectedFactor] = useState<number | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [fRes, fiRes] = await Promise.all([
        fetchFactors(),
        fetchFeatureImportance(runId),
      ])
      setFactors(fRes.factors)
      setFeatures(fiRes.features)
      setLoading(false)
    }
    load()
  }, [runId])

  if (loading) return <div className="text-center text-slate-400 py-12">Loading...</div>

  const active = factors.filter((f) => f.status === 'active').length
  const monitoring = factors.filter((f) => f.status === 'monitoring').length
  const bestPsr = factors.length > 0 ? Math.max(...factors.map((f) => f.psr)) : 0
  const bestFormula = factors.find((f) => f.psr === bestPsr)?.formula ?? '-'

  return (
    <div>
      <div className="grid grid-cols-4 gap-3 mb-5">
        <Metric label="Factors Tested" value={factors.length.toLocaleString()} sub="this training run" />
        <Metric label="Active Factors" value={String(active)} color="text-green-500" sub="PSR > 0.85" />
        <Metric label="Monitoring" value={String(monitoring)} color="text-amber-500" sub="PSR 0.70-0.85" />
        <Metric label="Best PSR" value={bestPsr.toFixed(2)} color="text-cyan-500" sub={bestFormula} />
      </div>

      {/* Factors Table */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 mb-5">
        <div className="flex items-center gap-2 mb-4">
          <SectionTitle tag="AlphaGPT">Discovered Factors</SectionTitle>
          <MockBadge />
        </div>
        <FactorsTable
          factors={factors}
          selectedFactor={selectedFactor}
          onSelect={(id) => setSelectedFactor(id === selectedFactor ? null : id)}
        />
      </div>

      {/* Feature Importance */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
        <SectionTitle tag="AFML Ch. 8">Feature Importance (MDA)</SectionTitle>
        <div className="text-[11px] text-slate-500 mb-3.5">
          Mean Decrease Accuracy — permutation-based importance with Purged K-Fold CV
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart layout="vertical" data={features}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis type="number" tick={{ fontSize: 10, fill: '#475569' }} domain={[0, 'auto']} />
            <YAxis dataKey="feature_name" type="category" tick={{ fontSize: 11, fill: '#64748b' }} width={120} />
            <Tooltip content={<ChartTooltip />} />
            <Bar dataKey="importance" radius={[0, 4, 4, 0]} name="MDA Score">
              {features.map((_, i) => (
                <Cell key={i} fill={IMPORTANCE_COLORS[i % IMPORTANCE_COLORS.length]} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function FactorsTable({
  factors,
  selectedFactor,
  onSelect,
}: {
  factors: DiscoveredFactor[]
  selectedFactor: number | null
  onSelect: (id: number) => void
}) {
  const statusColor = (s: string): 'green' | 'amber' | 'red' => {
    if (s === 'active') return 'green'
    if (s === 'monitoring') return 'amber'
    return 'red'
  }

  return (
    <table className="w-full border-collapse text-[13px]">
      <thead>
        <tr className="border-b border-slate-700">
          {['#', 'Formula (RPN)', 'PSR', 'Sharpe', 'Max DD', 'Trades', 'Status'].map((h) => (
            <th key={h} className="text-left px-3 py-2 text-[11px] text-slate-500 font-semibold uppercase tracking-wide">
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {factors.map((f) => (
          <tr
            key={f.id}
            onClick={() => onSelect(f.id)}
            className={`border-b border-slate-700/20 cursor-pointer transition-colors ${
              selectedFactor === f.id ? 'bg-slate-800' : 'hover:bg-slate-800/50'
            }`}
          >
            <td className="px-3 py-2.5 text-slate-600 font-mono">{f.id}</td>
            <td className="px-3 py-2.5 font-mono text-xs text-cyan-500">{f.formula}</td>
            <td className="px-3 py-2.5">
              <PsrBar value={f.psr} />
            </td>
            <td className="px-3 py-2.5 font-mono">{f.sharpe.toFixed(2)}</td>
            <td className="px-3 py-2.5 font-mono text-red-500">{f.max_dd}%</td>
            <td className="px-3 py-2.5 font-mono text-slate-500">{f.trades}</td>
            <td className="px-3 py-2.5">
              <Pill color={statusColor(f.status)}>{f.status}</Pill>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function PsrBar({ value }: { value: number }) {
  const color = value > 0.85 ? 'bg-green-500' : value > 0.7 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2">
      <div className="w-[50px] h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value * 100}%` }} />
      </div>
      <span className="font-mono font-semibold">{value.toFixed(2)}</span>
    </div>
  )
}
