const COLOR_MAP: Record<string, string> = {
  cyan: 'bg-cyan-500/10 border-cyan-500/30 text-cyan-500',
  green: 'bg-green-500/10 border-green-500/30 text-green-500',
  red: 'bg-red-500/10 border-red-500/30 text-red-500',
  amber: 'bg-amber-500/10 border-amber-500/30 text-amber-500',
  violet: 'bg-violet-400/10 border-violet-400/30 text-violet-400',
  blue: 'bg-blue-500/10 border-blue-500/30 text-blue-500',
  pink: 'bg-pink-400/10 border-pink-400/30 text-pink-400',
  slate: 'bg-slate-500/10 border-slate-500/30 text-slate-500',
}

interface PillProps {
  children: React.ReactNode
  color?: keyof typeof COLOR_MAP
}

export default function Pill({ children, color = 'cyan' }: PillProps) {
  const classes = COLOR_MAP[color] ?? COLOR_MAP.cyan
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-[11px] font-semibold tracking-wide uppercase border ${classes}`}>
      {children}
    </span>
  )
}
