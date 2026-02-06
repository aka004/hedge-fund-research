import type { TooltipProps } from 'recharts'

export default function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-slate-900 border border-slate-700 rounded-md px-3.5 py-2.5 text-xs shadow-lg shadow-black/40">
      <div className="text-slate-500 mb-1.5 text-[11px]">{label}</div>
      {payload.map((p, i) => (
        <div key={i} className="flex justify-between gap-4" style={{ color: p.color }}>
          <span>{p.name}</span>
          <span className="font-semibold font-mono">
            {typeof p.value === 'number'
              ? p.value > 100
                ? `$${p.value.toLocaleString()}`
                : p.value.toFixed(2)
              : p.value}
          </span>
        </div>
      ))}
    </div>
  )
}
