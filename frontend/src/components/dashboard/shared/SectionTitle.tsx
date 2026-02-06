import Pill from './Pill'

interface SectionTitleProps {
  children: React.ReactNode
  tag?: string
}

export default function SectionTitle({ children, tag }: SectionTitleProps) {
  return (
    <div className="flex items-center gap-2.5 mb-4">
      <h2 className="text-base font-bold text-slate-200 tracking-tight">{children}</h2>
      {tag && <Pill color="slate">{tag}</Pill>}
    </div>
  )
}
