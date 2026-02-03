import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import type { PricePoint, Technicals } from '../types/stock'

interface RSIChartProps {
  priceHistory: PricePoint[]
  currentRSI: number | null
}

export default function RSIChart({ priceHistory, currentRSI }: RSIChartProps) {
  // Calculate RSI for historical data
  // This is a simplified calculation - ideally would be calculated on backend
  const calculateRSI = (prices: number[], period = 14) => {
    if (prices.length < period + 1) return []

    const rsiValues: (number | null)[] = new Array(period).fill(null)

    for (let i = period; i < prices.length; i++) {
      let gains = 0
      let losses = 0

      for (let j = 0; j < period; j++) {
        const change = prices[i - j] - prices[i - j - 1]
        if (change > 0) gains += change
        else losses -= change
      }

      const avgGain = gains / period
      const avgLoss = losses / period

      if (avgLoss === 0) {
        rsiValues.push(100)
      } else {
        const rs = avgGain / avgLoss
        const rsi = 100 - 100 / (1 + rs)
        rsiValues.push(rsi)
      }
    }

    return rsiValues
  }

  const prices = priceHistory.map(p => p.close)
  const rsiValues = calculateRSI(prices, 14)

  const chartData = priceHistory.map((point, index) => ({
    date: new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    rsi: rsiValues[index],
  }))

  // Get RSI zone color
  const getRSIColor = (rsi: number | null) => {
    if (!rsi) return '#6B7280'
    if (rsi >= 70) return '#EF4444' // Overbought - red
    if (rsi <= 30) return '#10B981' // Oversold - green
    return '#3B82F6' // Neutral - blue
  }

  const currentRSIColor = getRSIColor(currentRSI)

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold">RSI (14)</h3>
        {currentRSI !== null && (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-400">Current:</span>
            <span className={`text-lg font-bold`} style={{ color: currentRSIColor }}>
              {currentRSI.toFixed(2)}
            </span>
            <span className="text-xs text-slate-500">
              {currentRSI >= 70
                ? '(Overbought)'
                : currentRSI <= 30
                ? '(Oversold)'
                : '(Neutral)'}
            </span>
          </div>
        )}
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <defs>
            <linearGradient id="rsiGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.8} />
              <stop offset="95%" stopColor="#3B82F6" stopOpacity={0.1} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="date"
            stroke="#9CA3AF"
            tick={{ fontSize: 12 }}
            tickFormatter={(value, index) => {
              return index % 15 === 0 ? value : ''
            }}
          />
          <YAxis
            stroke="#9CA3AF"
            tick={{ fontSize: 12 }}
            domain={[0, 100]}
            ticks={[0, 30, 50, 70, 100]}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1E293B',
              border: '1px solid #475569',
              borderRadius: '0.5rem',
              color: '#E2E8F0',
            }}
            formatter={(value: any) => [value?.toFixed(2), 'RSI']}
            labelStyle={{ color: '#94A3B8' }}
          />
          <ReferenceLine y={70} stroke="#EF4444" strokeDasharray="3 3" label="Overbought" />
          <ReferenceLine y={30} stroke="#10B981" strokeDasharray="3 3" label="Oversold" />
          <ReferenceLine y={50} stroke="#6B7280" strokeDasharray="3 3" />
          <Area
            type="monotone"
            dataKey="rsi"
            stroke="#3B82F6"
            fillOpacity={1}
            fill="url(#rsiGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
