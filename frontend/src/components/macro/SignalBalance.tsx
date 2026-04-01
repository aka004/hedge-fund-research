import type { SignalBalance as SignalBalanceType } from '../../lib/macroApi'

const REGIME_COLORS: Record<string, string> = {
  HAWKISH: '#ff3b30',
  DOVISH: '#00d26a',
  MIXED: '#ff8c00',
}

interface Props {
  balance: SignalBalanceType
}

function DonutChart({ balance }: { balance: SignalBalanceType }) {
  const total = balance.total || 1
  const radius = 50
  const strokeWidth = 12
  const cx = 60
  const cy = 60
  const circumference = 2 * Math.PI * radius

  const segments = [
    { count: balance.hawkish, color: '#ff3b30' },
    { count: balance.dovish, color: '#00d26a' },
    { count: balance.neutral, color: '#555' },
  ]

  let offset = 0

  return (
    <svg width={120} height={120} viewBox="0 0 120 120">
      {/* Background ring */}
      <circle
        cx={cx}
        cy={cy}
        r={radius}
        fill="none"
        stroke="#1a1a1a"
        strokeWidth={strokeWidth}
      />
      {segments.map((seg, i) => {
        const pct = seg.count / total
        const dashLen = pct * circumference
        const dashOffset = -offset * circumference
        offset += pct
        if (seg.count === 0) return null
        return (
          <circle
            key={i}
            cx={cx}
            cy={cy}
            r={radius}
            fill="none"
            stroke={seg.color}
            strokeWidth={strokeWidth}
            strokeDasharray={`${dashLen} ${circumference - dashLen}`}
            strokeDashoffset={dashOffset}
            transform={`rotate(-90 ${cx} ${cy})`}
            style={{ transition: 'stroke-dasharray 0.5s' }}
          />
        )
      })}
      {/* Center text */}
      <text
        x={cx}
        y={cy - 4}
        textAnchor="middle"
        fill="#fff"
        fontSize="16"
        fontFamily="'IBM Plex Mono', monospace"
        fontWeight="600"
      >
        {balance.total}
      </text>
      <text
        x={cx}
        y={cy + 10}
        textAnchor="middle"
        fill="#555"
        fontSize="8"
        fontFamily="'JetBrains Mono', monospace"
      >
        SIGNALS
      </text>
    </svg>
  )
}

export function SignalBalance({ balance }: Props) {
  const regimeColor = REGIME_COLORS[balance.regime] ?? '#888'
  const total = balance.total || 1

  return (
    <div
      style={{
        background: '#0d0d0d',
        border: '1px solid #1a1a1a',
        borderRadius: '2px',
        padding: '16px',
      }}
    >
      {/* Header */}
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
          fontWeight: 700,
          color: '#ff8c00',
          textTransform: 'uppercase',
          letterSpacing: '1px',
          marginBottom: '16px',
        }}
      >
        Signal Balance
      </div>

      {/* Donut */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
        <DonutChart balance={balance} />
      </div>

      {/* Counts */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-around',
          marginBottom: '16px',
          fontFamily: "'IBM Plex Mono', monospace",
          fontSize: '12px',
        }}
      >
        <div style={{ textAlign: 'center' }}>
          <div style={{ color: '#ff3b30', fontWeight: 600 }}>{balance.hawkish}</div>
          <div style={{ color: '#555', fontSize: '9px', fontFamily: "'JetBrains Mono', monospace" }}>HAWK</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ color: '#00d26a', fontWeight: 600 }}>{balance.dovish}</div>
          <div style={{ color: '#555', fontSize: '9px', fontFamily: "'JetBrains Mono', monospace" }}>DOVE</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ color: '#888', fontWeight: 600 }}>{balance.neutral}</div>
          <div style={{ color: '#555', fontSize: '9px', fontFamily: "'JetBrains Mono', monospace" }}>NEUT</div>
        </div>
      </div>

      {/* Regime badge */}
      <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '16px' }}>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            fontWeight: 700,
            color: regimeColor,
            border: `1px solid ${regimeColor}`,
            borderRadius: '12px',
            padding: '4px 16px',
            letterSpacing: '1px',
          }}
        >
          {balance.regime}
        </span>
      </div>

      {/* Stacked bar */}
      <div
        style={{
          display: 'flex',
          height: '6px',
          borderRadius: '3px',
          overflow: 'hidden',
          background: '#1a1a1a',
        }}
      >
        <div
          style={{
            width: `${(balance.hawkish / total) * 100}%`,
            background: '#ff3b30',
            transition: 'width 0.4s',
          }}
        />
        <div
          style={{
            width: `${(balance.dovish / total) * 100}%`,
            background: '#00d26a',
            transition: 'width 0.4s',
          }}
        />
        <div
          style={{
            width: `${(balance.neutral / total) * 100}%`,
            background: '#555',
            transition: 'width 0.4s',
          }}
        />
      </div>
    </div>
  )
}
