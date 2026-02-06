import { useState, useEffect, useMemo } from 'react'
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from 'recharts'
import type {
  CVPathsResponse, ValidationCheck, BootstrapComparison,
} from '../../types/dashboard'
import {
  fetchCVPaths, fetchValidationChecklist, fetchBootstrapComparison,
  fetchDashboardOverview,
} from '../../lib/dashboardApi'
import Metric from './shared/Metric'
import SectionTitle from './shared/SectionTitle'
import ChartTooltip from './shared/ChartTooltip'

const PATH_COLORS = ['#06b6d4', '#22c55e', '#a78bfa', '#f59e0b', '#f472b6', '#3b82f6', '#ef4444', '#64748b']

interface ValidationTabProps {
  runId?: string
}

export default function ValidationTab({ runId }: ValidationTabProps) {
  const [cvData, setCvData] = useState<CVPathsResponse | null>(null)
  const [checks, setChecks] = useState<ValidationCheck[]>([])
  const [bootstrap, setBootstrap] = useState<BootstrapComparison[]>([])
  const [psr, setPsr] = useState(0)
  const [deflatedSR, setDeflatedSR] = useState(0)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      setLoading(true)
      const [cv, cl, bs, ov] = await Promise.all([
        fetchCVPaths(runId),
        fetchValidationChecklist(runId),
        fetchBootstrapComparison(runId),
        fetchDashboardOverview(runId),
      ])
      setCvData(cv)
      setChecks(cl.checks)
      setBootstrap(bs.comparisons)
      setPsr(ov.psr)
      setDeflatedSR(ov.deflated_sharpe)
      setLoading(false)
    }
    load()
  }, [runId])

  // Transform CV paths into chart data: each row = { day, path0, path1, ... }
  const chartData = useMemo(() => {
    if (!cvData?.paths.length) return []
    const maxLen = Math.max(...cvData.paths.map((p) => p.equity_curve.length))
    return Array.from({ length: maxLen }, (_, day) => {
      const row: Record<string, number> = { day }
      cvData.paths.forEach((p) => {
        row[`path${p.path_id}`] = p.equity_curve[day] ?? p.equity_curve[p.equity_curve.length - 1]
      })
      return row
    })
  }, [cvData])

  if (loading) return <div className="text-center text-slate-400 py-12">Loading...</div>

  const pbo = cvData?.pbo ?? 0

  return (
    <div>
      <div className="grid grid-cols-4 gap-3 mb-5">
        <Metric label="Probabilistic SR" value={psr.toFixed(2)} color="text-green-500" sub={`P(SR > 0) = ${(psr * 100).toFixed(0)}%`} />
        <Metric label="Deflated SR" value={deflatedSR.toFixed(2)} color="text-cyan-500" sub="adjusted for multiple testing" />
        <Metric
          label="P(Backtest Overfit)"
          value={`${(pbo * 100).toFixed(0)}%`}
          color={pbo < 0.2 ? 'text-green-500' : 'text-red-500'}
          sub="CSCV method"
        />
        <Metric label="CV Folds" value={String(cvData?.n_paths ?? 8)} sub="CPCV paths" />
      </div>

      {/* CPCV Chart */}
      <div className="bg-slate-900 rounded-lg border border-slate-700 p-4 mb-5">
        <SectionTitle tag="AFML Ch. 12">Combinatorial Purged CV — Backtest Paths</SectionTitle>
        <div className="text-[11px] text-slate-500 mb-3.5 leading-relaxed">
          Out-of-sample equity paths from CPCV. Paths below 1.0 indicate periods of underperformance.
        </div>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
            <XAxis dataKey="day" tick={{ fontSize: 10, fill: '#475569' }} />
            <YAxis tick={{ fontSize: 10, fill: '#475569' }} domain={['auto', 'auto']} />
            <Tooltip content={<ChartTooltip />} />
            <ReferenceLine y={1} stroke="#475569" strokeDasharray="4 4" />
            {cvData?.paths.map((p, i) => (
              <Line
                key={p.path_id}
                type="monotone"
                dataKey={`path${p.path_id}`}
                stroke={PATH_COLORS[i % PATH_COLORS.length]}
                strokeWidth={1.5}
                dot={false}
                name={`Path ${p.path_id + 1}`}
                opacity={0.7}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Two-column grid */}
      <div className="grid grid-cols-2 gap-4">
        <ChecklistPanel checks={checks} />
        <BootstrapPanel comparisons={bootstrap} />
      </div>
    </div>
  )
}

function ChecklistPanel({ checks }: { checks: ValidationCheck[] }) {
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
      <SectionTitle tag="AFML Ch. 11">Backtest Checklist</SectionTitle>
      {checks.map((item, i) => (
        <div
          key={i}
          className={`flex items-center gap-2.5 py-2 text-[13px] ${i < checks.length - 1 ? 'border-b border-slate-700/20' : ''}`}
        >
          <span className={`text-base ${item.passed ? 'text-green-500' : 'text-red-500'}`}>
            {item.passed ? '\u2713' : '\u2717'}
          </span>
          <span className={item.passed ? 'text-slate-200' : 'text-slate-500'}>{item.check}</span>
        </div>
      ))}
    </div>
  )
}

function BootstrapPanel({ comparisons }: { comparisons: BootstrapComparison[] }) {
  const colors = ['#ef4444', '#22c55e', '#06b6d4']
  return (
    <div className="bg-slate-900 rounded-lg border border-slate-700 p-4">
      <SectionTitle tag="AFML Ch. 4">Sequential Bootstrap</SectionTitle>
      <div className="text-xs text-slate-500 mb-3 leading-relaxed">
        Average uniqueness via sequential vs standard bootstrap. Higher uniqueness = less information leakage.
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={comparisons}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="method" tick={{ fontSize: 11, fill: '#64748b' }} />
          <YAxis tick={{ fontSize: 10, fill: '#475569' }} domain={[0, 1]} />
          <Tooltip content={<ChartTooltip />} />
          <Bar dataKey="uniqueness" radius={[4, 4, 0, 0]} name="Avg Uniqueness">
            {comparisons.map((_, i) => (
              <Cell key={i} fill={colors[i % colors.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
