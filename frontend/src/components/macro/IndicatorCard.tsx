import type { IndicatorData } from '../../lib/macroApi'

const SIGNAL_COLORS: Record<string, string> = {
  hawkish: '#ff3b30',
  dovish: '#00d26a',
  neutral: '#888',
}

const TREND_ARROWS: Record<string, string> = {
  up: '\u25B2',
  down: '\u25BC',
  flat: '\u25C6',
}

interface Props {
  indicator: IndicatorData
  onSelect: (id: string) => void
}

export function IndicatorCard({ indicator, onSelect }: Props) {
  const signalColor = SIGNAL_COLORS[indicator.signal] ?? '#888'
  const trendArrow = TREND_ARROWS[indicator.trend] ?? ''
  const sparkline = indicator.sparkline ?? []
  const sparkMax = Math.max(...sparkline, 1)

  return (
    <button
      onClick={() => onSelect(indicator.id)}
      style={{
        background: '#0d0d0d',
        border: '1px solid #1a1a1a',
        borderRadius: '2px',
        padding: '10px 12px',
        cursor: 'pointer',
        textAlign: 'left',
        width: '100%',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = '#333'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = '#1a1a1a'
      }}
    >
      {/* Header row: name + signal dot */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '10px',
            color: '#666',
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }}
        >
          {indicator.name}
        </span>
        <span
          style={{
            width: '6px',
            height: '6px',
            borderRadius: '50%',
            backgroundColor: signalColor,
            boxShadow: `0 0 6px ${signalColor}80`,
            display: 'inline-block',
            flexShrink: 0,
          }}
        />
      </div>

      {/* Value */}
      <div
        style={{
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: '20px',
          fontWeight: 600,
          color: signalColor,
          lineHeight: 1.2,
          marginBottom: '6px',
        }}
      >
        {indicator.display}
      </div>

      {/* Bottom row: date + trend */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '9px',
          color: '#555',
        }}
      >
        <span>{indicator.date}</span>
        <span style={{ color: signalColor }}>
          {trendArrow} {indicator.trend_display}
        </span>
      </div>

      {/* Sparkline */}
      {sparkline.length > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: '1px',
            height: '16px',
            marginTop: '6px',
          }}
        >
          {sparkline.map((val, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                height: `${Math.max((val / sparkMax) * 100, 4)}%`,
                backgroundColor: `${signalColor}60`,
                borderRadius: '1px 1px 0 0',
                minHeight: '1px',
              }}
            />
          ))}
        </div>
      )}
    </button>
  )
}
