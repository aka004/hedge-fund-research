import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchStockDetail } from '../lib/api'
import { formatCurrency, formatPercent, formatNumber, getPriceChangeColor } from '../lib/formatters'
import type { StockDetail } from '../types/stock'

export default function StockDetailPage() {
  const { ticker } = useParams<{ ticker: string }>()
  const navigate = useNavigate()
  const [stock, setStock] = useState<StockDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!ticker) return

    const loadStock = async () => {
      setLoading(true)
      setError(null)

      try {
        const data = await fetchStockDetail(ticker.toUpperCase())
        setStock(data)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load stock')
      } finally {
        setLoading(false)
      }
    }

    loadStock()
  }, [ticker])

  if (loading) {
    return (
      <div className="min-h-screen bg-slate-900 text-slate-200 flex items-center justify-center">
        <div>Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-slate-900 text-slate-200">
        <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
          <button
            onClick={() => navigate('/screener')}
            className="text-blue-500 hover:text-blue-400"
          >
            ← Back to Screener
          </button>
        </header>
        <main className="container mx-auto px-6 py-8">
          <div className="bg-red-900/20 border border-red-900 rounded-lg p-8 text-center text-red-400">
            {error}
          </div>
        </main>
      </div>
    )
  }

  if (!stock) return null

  const { company, price, price_change, price_change_pct, fundamentals, technicals } = stock

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 px-6 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-6">
            <button
              onClick={() => navigate('/screener')}
              className="text-blue-500 hover:text-blue-400"
            >
              ← Back
            </button>
            <div>
              <div className="flex items-center gap-3">
                <div className="text-2xl font-bold">{company.ticker}</div>
                {company.exchange && (
                  <span className="px-2 py-1 text-xs bg-slate-700 rounded">{company.exchange}</span>
                )}
              </div>
              <div className="text-sm text-slate-400">{company.name}</div>
            </div>
          </div>
          <div className="text-right">
            {price && (
              <>
                <div className="text-3xl font-bold">${price.toFixed(2)}</div>
                {price_change_pct !== undefined && price_change_pct !== null && (
                  <div className={`text-sm ${getPriceChangeColor(price_change_pct)}`}>
                    {price_change_pct >= 0 ? '+' : ''}
                    {price_change?.toFixed(2)} ({price_change_pct.toFixed(2)}%)
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-6 py-8">
        {/* Quick Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <QuickStat label="Market Cap" value={formatCurrency(company.market_cap)} />
          <QuickStat label="P/E Ratio" value={formatNumber(fundamentals.pe_ratio)} />
          <QuickStat label="Forward P/E" value={formatNumber(fundamentals.forward_pe)} />
          <QuickStat label="Beta" value={formatNumber(technicals.beta)} />
          <QuickStat label="Dividend Yield" value={formatPercent(fundamentals.dividend_yield)} />
          <QuickStat label="ROE" value={formatPercent(fundamentals.roe)} />
          <QuickStat label="Debt/Equity" value={formatNumber(fundamentals.debt_equity)} />
          <QuickStat label="RSI (14)" value={formatNumber(technicals.rsi_14)} />
        </div>

        {/* Metrics Sections */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Valuation */}
          <MetricsSection title="Valuation">
            <MetricRow label="P/E Ratio" value={formatNumber(fundamentals.pe_ratio)} />
            <MetricRow label="Forward P/E" value={formatNumber(fundamentals.forward_pe)} />
            <MetricRow label="PEG Ratio" value={formatNumber(fundamentals.peg_ratio)} />
            <MetricRow label="P/B Ratio" value={formatNumber(fundamentals.pb_ratio)} />
            <MetricRow label="P/S Ratio" value={formatNumber(fundamentals.ps_ratio)} />
            <MetricRow label="EV/EBITDA" value={formatNumber(fundamentals.ev_ebitda)} />
          </MetricsSection>

          {/* Profitability */}
          <MetricsSection title="Profitability">
            <MetricRow label="ROE" value={formatPercent(fundamentals.roe)} />
            <MetricRow label="ROA" value={formatPercent(fundamentals.roa)} />
            <MetricRow label="ROIC" value={formatPercent(fundamentals.roic)} />
            <MetricRow label="Gross Margin" value={formatPercent(fundamentals.gross_margin)} />
            <MetricRow label="Operating Margin" value={formatPercent(fundamentals.operating_margin)} />
            <MetricRow label="Net Margin" value={formatPercent(fundamentals.net_margin)} />
          </MetricsSection>

          {/* Growth */}
          <MetricsSection title="Growth">
            <MetricRow label="Revenue Growth (YoY)" value={formatPercent(fundamentals.revenue_growth_yoy)} />
            <MetricRow label="Revenue Growth (QoQ)" value={formatPercent(fundamentals.revenue_growth_qoq)} />
            <MetricRow label="Earnings Growth (YoY)" value={formatPercent(fundamentals.earnings_growth_yoy)} />
          </MetricsSection>

          {/* Financial Health */}
          <MetricsSection title="Financial Health">
            <MetricRow label="Debt/Equity" value={formatNumber(fundamentals.debt_equity)} />
            <MetricRow label="Current Ratio" value={formatNumber(fundamentals.current_ratio)} />
            <MetricRow label="Quick Ratio" value={formatNumber(fundamentals.quick_ratio)} />
          </MetricsSection>

          {/* Technicals */}
          <MetricsSection title="Technical Indicators">
            <MetricRow label="SMA 20" value={formatNumber(technicals.sma_20)} />
            <MetricRow label="SMA 50" value={formatNumber(technicals.sma_50)} />
            <MetricRow label="SMA 200" value={formatNumber(technicals.sma_200)} />
            <MetricRow label="RSI (14)" value={formatNumber(technicals.rsi_14)} />
            <MetricRow label="MACD" value={formatNumber(technicals.macd)} />
            <MetricRow label="Beta" value={formatNumber(technicals.beta)} />
          </MetricsSection>

          {/* Dividends */}
          {fundamentals.dividend_yield && (
            <MetricsSection title="Dividends">
              <MetricRow label="Yield" value={formatPercent(fundamentals.dividend_yield)} />
              <MetricRow label="Payout Ratio" value={formatPercent(fundamentals.payout_ratio)} />
            </MetricsSection>
          )}
        </div>

        {/* Company Info Footer */}
        {company.description && (
          <div className="mt-8 bg-slate-800 border border-slate-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-3">About {company.name}</h3>
            <div className="flex flex-wrap gap-2 mb-4">
              {company.sector && <span className="px-3 py-1 bg-slate-700 rounded-full text-sm">{company.sector}</span>}
              {company.industry && <span className="px-3 py-1 bg-slate-700 rounded-full text-sm">{company.industry}</span>}
            </div>
            <p className="text-slate-300 mb-4">{company.description}</p>
            <div className="flex gap-6 text-sm text-slate-400">
              {company.website && <a href={company.website} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-400">Website →</a>}
              {company.employees && <span>{company.employees.toLocaleString()} employees</span>}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}

function QuickStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <div className="text-xs text-slate-400 mb-1">{label}</div>
      <div className="text-lg font-semibold">{value}</div>
    </div>
  )
}

function MetricsSection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-6">
      <h3 className="text-lg font-semibold mb-4">{title}</h3>
      <div className="space-y-2">
        {children}
      </div>
    </div>
  )
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between text-sm">
      <span className="text-slate-400">{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  )
}
