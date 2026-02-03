import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import type { PricePoint, Technicals } from '../types/stock'

interface PriceChartProps {
  priceHistory: PricePoint[]
  technicals: Technicals
}

export default function PriceChart({ priceHistory, technicals }: PriceChartProps) {
  // Calculate SMAs for the price history
  const chartData = priceHistory.map((point, index) => {
    const data: any = {
      date: new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      price: point.close,
    }

    // Add SMA lines (only show recent values from technicals)
    if (index === priceHistory.length - 1) {
      if (technicals.sma_20) data.sma20 = technicals.sma_20
      if (technicals.sma_50) data.sma50 = technicals.sma_50
      if (technicals.sma_200) data.sma200 = technicals.sma_200
    }

    return data
  })

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

  const enrichedData = priceHistory.map((point, index) => ({
    date: new Date(point.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    price: point.close,
    sma20: sma20Values[index],
    sma50: sma50Values[index],
    sma200: sma200Values[index],
  }))

  const minPrice = Math.min(...priceHistory.map(p => p.close))
  const maxPrice = Math.max(...priceHistory.map(p => p.close))
  const padding = (maxPrice - minPrice) * 0.1

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4">Price History (90 Days)</h3>
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={enrichedData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis
            dataKey="date"
            stroke="#9CA3AF"
            tick={{ fontSize: 12 }}
            interval="preserveStartEnd"
            tickFormatter={(value, index) => {
              // Show only every 15th label to avoid crowding
              return index % 15 === 0 ? value : ''
            }}
          />
          <YAxis
            stroke="#9CA3AF"
            tick={{ fontSize: 12 }}
            domain={[minPrice - padding, maxPrice + padding]}
            tickFormatter={(value) => `$${value.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: '#1E293B',
              border: '1px solid #475569',
              borderRadius: '0.5rem',
              color: '#E2E8F0',
            }}
            formatter={(value: any) => [`$${value.toFixed(2)}`, '']}
            labelStyle={{ color: '#94A3B8' }}
          />
          <Legend
            wrapperStyle={{ color: '#94A3B8', paddingTop: '10px' }}
            formatter={(value) => {
              const labels: any = {
                price: 'Price',
                sma20: 'SMA 20',
                sma50: 'SMA 50',
                sma200: 'SMA 200',
              }
              return labels[value] || value
            }}
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#3B82F6"
            strokeWidth={2}
            dot={false}
            name="Price"
          />
          <Line
            type="monotone"
            dataKey="sma20"
            stroke="#10B981"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="5 5"
            name="SMA 20"
          />
          <Line
            type="monotone"
            dataKey="sma50"
            stroke="#F59E0B"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="5 5"
            name="SMA 50"
          />
          <Line
            type="monotone"
            dataKey="sma200"
            stroke="#EF4444"
            strokeWidth={1.5}
            dot={false}
            strokeDasharray="5 5"
            name="SMA 200"
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
