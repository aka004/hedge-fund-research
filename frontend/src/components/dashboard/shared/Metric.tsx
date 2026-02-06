interface MetricProps {
  label: string
  value: string
  sub?: string
  color?: string
}

export default function Metric({ label, value, sub, color = 'text-slate-200' }: MetricProps) {
  return (
    <div className="p-3 bg-slate-900 rounded-lg border border-slate-700">
      <div className="text-[11px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`text-xl font-bold font-mono ${color}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-600 mt-0.5">{sub}</div>}
    </div>
  )
}
