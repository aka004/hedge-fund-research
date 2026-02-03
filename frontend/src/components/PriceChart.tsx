import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { PricePoint, Technicals } from '../types/stock'

interface PriceChartProps {
  priceHistory: PricePoint[]
  technicals: Technicals
}

export default function PriceChart({ priceHistory, technicals }: PriceChartProps) {
  // Calculate SMAs manually for better visualization
  const calculateSMA = (data: PricePoint[], period: number) => {
    return data.map((_, index) => {
      if (index < period - 1) return null
      const slice = data.slice(index - period + 1, index + 1)
      const sum = slice.reduce((acc, p) => acc + p.close, 0)
      return sum / period
    })
  }

  const sma20Values = calculateSMA(priceHistory, 20)
  const sma50Values = calculateSMA(priceHistory, 50)
  const sma200Values = calculateSMA(priceHistory, 200)

  // Prepare chart data with all values
  const chartData = priceHistory.map((point, index) => ({
    date: new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    price: point.close,
    sma20: sma20Values[index],
    sma50: sma50Values[index],
    sma200: sma200Values[index],
  }))

  // Calculate Y-axis domain with padding
  const allPrices = priceHistory.map(p => p.close)
  const minPrice = Math.min(...allPrices)
  const maxPrice = Math.max(...allPrices)
  const padding = (maxPrice - minPrice) * 0.1

  // Custom tooltip
  const CustomTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 shadow-xl">
          <p className="text-slate-400 text-sm mb-2">{label}</p>
          {payload.map((entry: any, index: number) => {
            if (entry.value != null) {
              return (
                <p key={index} className="text-sm" style={{ color: entry.color }}>
                  {entry.name}: ${entry.value.toFixed(2)}
                </p>
              )
            }
            return null
          })}
        </div>
      )
    }
    return null
  }

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4 text-slate-100">Price History (90 Days)</h3>
      <div style={{ width: '100%', height: 400 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart 
            data={chartData} 
            margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#475569" opacity={0.3} />
            <XAxis
              dataKey="date"
              stroke="#94A3B8"
              tick={{ fill: '#94A3B8', fontSize: 12 }}
              tickLine={{ stroke: '#475569' }}
              interval="preserveStartEnd"
              minTickGap={30}
            />
            <YAxis
              stroke="#94A3B8"
              tick={{ fill: '#94A3B8', fontSize: 12 }}
              tickLine={{ stroke: '#475569' }}
              domain={[minPrice - padding, maxPrice + padding]}
              tickFormatter={(value) => `$${value.toFixed(0)}`}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend
              wrapperStyle={{ paddingTop: '20px' }}
              iconType="line"
              formatter={(value) => {
                const labels: any = {
                  price: 'Price',
                  sma20: 'SMA 20',
                  sma50: 'SMA 50',
                  sma200: 'SMA 200',
                }
                return <span className="text-slate-300 text-sm">{labels[value] || value}</span>
              }}
            />
            <Line
              type="monotone"
              dataKey="price"
              stroke="#3B82F6"
              strokeWidth={2.5}
              dot={false}
              name="Price"
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="sma20"
              stroke="#10B981"
              strokeWidth={2}
              dot={false}
              strokeDasharray="5 5"
              name="SMA 20"
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="sma50"
              stroke="#F59E0B"
              strokeWidth={2}
              dot={false}
              strokeDasharray="5 5"
              name="SMA 50"
              isAnimationActive={false}
              connectNulls
            />
            <Line
              type="monotone"
              dataKey="sma200"
              stroke="#EF4444"
              strokeWidth={2}
              dot={false}
              strokeDasharray="5 5"
              name="SMA 200"
              isAnimationActive={false}
              connectNulls
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
