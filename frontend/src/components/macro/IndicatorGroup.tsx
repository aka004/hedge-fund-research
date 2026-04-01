import type { IndicatorGroup as GroupType } from '../../lib/macroApi'
import { IndicatorCard } from './IndicatorCard'

interface Props {
  group: GroupType
  groupKey: string
  onSelectIndicator: (id: string) => void
}

const COLUMN_MAP: Record<string, number> = {
  inflation: 4,
  fed_policy: 3,
  markets: 3,
  employment: 2,
}

export function IndicatorGroup({ group, groupKey, onSelectIndicator }: Props) {
  const cols = COLUMN_MAP[groupKey] ?? 3

  return (
    <div style={{ marginBottom: '20px' }}>
      {/* Section header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: '10px',
        }}
      >
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            fontWeight: 700,
            color: group.color,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            whiteSpace: 'nowrap',
          }}
        >
          {group.label}
        </span>
        <div
          style={{
            flex: 1,
            height: '1px',
            background: `linear-gradient(to right, ${group.color}40, transparent)`,
          }}
        />
      </div>

      {/* Indicator grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, 1fr)`,
          gap: '8px',
        }}
      >
        {group.indicators.map((ind) => (
          <IndicatorCard
            key={ind.id}
            indicator={ind}
            onSelect={onSelectIndicator}
          />
        ))}
      </div>
    </div>
  )
}
