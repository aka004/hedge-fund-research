import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine as RechartRefLine,
  ResponsiveContainer,
} from 'recharts'
import type { HistoryResponse } from '../../lib/macroApi'

const RANGES = ['1Y', '2Y', '5Y', 'MAX'] as const

interface Props {
  history: HistoryResponse
  loading: boolean
  onRangeChange: (range: string) => void
  onClose: () => void
  lineColor?: string
}

export function IndicatorChart({
  history,
  loading,
  onRangeChange,
  onClose,
  lineColor = '#ff8c00',
}: Props) {
  return (
    <div
      style={{
        background: '#0d0d0d',
        border: '1px solid #1a1a1a',
        borderRadius: '2px',
        padding: '16px',
        marginBottom: '16px',
        animation: 'slideDown 0.2s ease-out',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '12px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '12px',
              color: '#ccc',
              fontWeight: 600,
            }}
          >
            {history.name}
          </span>
          <span
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '9px',
              color: '#555',
            }}
          >
            {history.series_id}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Range buttons */}
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => onRangeChange(r)}
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '10px',
                padding: '2px 8px',
                background: history.range === r ? '#1a1a1a' : 'transparent',
                border: `1px solid ${history.range === r ? '#333' : '#1a1a1a'}`,
                color: history.range === r ? '#fff' : '#555',
                cursor: 'pointer',
                borderRadius: '2px',
              }}
            >
              {r}
            </button>
          ))}

          {/* Close button */}
          <button
            onClick={onClose}
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '14px',
              background: 'transparent',
              border: 'none',
              color: '#555',
              cursor: 'pointer',
              padding: '0 4px',
              lineHeight: 1,
            }}
          >
            x
          </button>
        </div>
      </div>

      {/* Chart */}
      {loading ? (
        <div
          style={{
            height: '220px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            color: '#555',
          }}
        >
          Loading history...
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={history.data}>
            <CartesianGrid stroke="#1a1a1a" strokeDasharray="3 3" />
            <XAxis
              dataKey="date"
              tick={{ fill: '#666', fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
              axisLine={{ stroke: '#1a1a1a' }}
              tickLine={false}
              interval="preserveStartEnd"
              minTickGap={60}
            />
            <YAxis
              tick={{ fill: '#666', fontSize: 9, fontFamily: "'JetBrains Mono', monospace" }}
              axisLine={{ stroke: '#1a1a1a' }}
              tickLine={false}
              domain={['auto', 'auto']}
              width={50}
            />
            <Tooltip
              contentStyle={{
                background: '#111',
                border: '1px solid #333',
                borderRadius: '2px',
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: '11px',
              }}
              labelStyle={{ color: '#888' }}
              itemStyle={{ color: lineColor }}
            />
            {history.reference_lines
              .filter((rl) => rl.value != null)
              .map((rl, i) => (
                <RechartRefLine
                  key={i}
                  y={rl.value!}
                  stroke={rl.color}
                  strokeDasharray="6 3"
                  label={{
                    value: rl.label,
                    fill: rl.color,
                    fontSize: 9,
                    fontFamily: "'JetBrains Mono', monospace",
                    position: 'right',
                  }}
                />
              ))}
            <Line
              type="monotone"
              dataKey="value"
              stroke={lineColor}
              strokeWidth={1.5}
              dot={false}
              activeDot={{ r: 3, fill: lineColor }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
