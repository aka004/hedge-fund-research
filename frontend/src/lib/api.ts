import type { ScreenerRequest, ScreenerResponse, StockDetail } from '../types/stock'

const API_BASE = '/api'

export async function fetchScreener(request: ScreenerRequest): Promise<ScreenerResponse> {
  const response = await fetch(`${API_BASE}/screener`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`)
  }
  
  return response.json()
}

export async function fetchStockDetail(ticker: string): Promise<StockDetail> {
  const response = await fetch(`${API_BASE}/stock/${ticker}`)
  
  if (!response.ok) {
    throw new Error(`API error: ${response.statusText}`)
  }
  
  return response.json()
}
