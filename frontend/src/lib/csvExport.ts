import type { StockSummary } from '../types/stock'

/**
 * Converts stock data to CSV format and triggers download
 */
export function exportStocksToCSV(stocks: StockSummary[], filename?: string): void {
  if (stocks.length === 0) {
    alert('No stocks to export')
    return
  }

  // Define columns to export
  const columns = [
    { key: 'ticker', header: 'Ticker' },
    { key: 'name', header: 'Company Name' },
    { key: 'sector', header: 'Sector' },
    { key: 'industry', header: 'Industry' },
    { key: 'exchange', header: 'Exchange' },
    { key: 'price', header: 'Price' },
    { key: 'price_change_pct', header: 'Change %' },
    { key: 'market_cap', header: 'Market Cap' },
    { key: 'volume', header: 'Volume' },
    { key: 'pe_ratio', header: 'P/E Ratio' },
    { key: 'forward_pe', header: 'Forward P/E' },
    { key: 'peg_ratio', header: 'PEG Ratio' },
    { key: 'pb_ratio', header: 'P/B Ratio' },
    { key: 'ps_ratio', header: 'P/S Ratio' },
    { key: 'roe', header: 'ROE' },
    { key: 'roa', header: 'ROA' },
    { key: 'gross_margin', header: 'Gross Margin' },
    { key: 'operating_margin', header: 'Operating Margin' },
    { key: 'net_margin', header: 'Net Margin' },
    { key: 'revenue_growth_yoy', header: 'Revenue Growth YoY' },
    { key: 'earnings_growth_yoy', header: 'Earnings Growth YoY' },
    { key: 'debt_equity', header: 'Debt/Equity' },
    { key: 'current_ratio', header: 'Current Ratio' },
    { key: 'dividend_yield', header: 'Dividend Yield' },
    { key: 'payout_ratio', header: 'Payout Ratio' },
    { key: 'rsi_14', header: 'RSI (14)' },
    { key: 'beta', header: 'Beta' },
    { key: 'sma_20', header: 'SMA 20' },
    { key: 'sma_50', header: 'SMA 50' },
    { key: 'sma_200', header: 'SMA 200' },
  ]

  // Create CSV header
  const header = columns.map(col => `"${col.header}"`).join(',')

  // Create CSV rows
  const rows = stocks.map(stock => {
    return columns.map(col => {
      const value = stock[col.key as keyof StockSummary]
      
      // Handle null/undefined
      if (value === null || value === undefined) {
        return '""'
      }
      
      // Format numbers
      if (typeof value === 'number') {
        return value.toString()
      }
      
      // Escape strings
      if (typeof value === 'string') {
        return `"${value.replace(/"/g, '""')}"`
      }
      
      return `"${value}"`
    }).join(',')
  })

  // Combine header and rows
  const csv = [header, ...rows].join('\n')

  // Create blob and download
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  
  if (navigator.msSaveBlob) {
    // IE 10+
    navigator.msSaveBlob(blob, filename || getDefaultFilename())
  } else {
    link.href = URL.createObjectURL(blob)
    link.download = filename || getDefaultFilename()
    link.style.visibility = 'hidden'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }
}

/**
 * Generates a default filename with timestamp
 */
function getDefaultFilename(): string {
  const now = new Date()
  const timestamp = now.toISOString().replace(/:/g, '-').split('.')[0]
  return `stock-screener-${timestamp}.csv`
}
