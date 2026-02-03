export interface Filter {
  field: string
  operator: string
  value: any
}

export interface SortConfig {
  field: string
  direction: 'asc' | 'desc'
}

export interface StockSummary {
  ticker: string
  name: string
  sector?: string
  industry?: string
  exchange?: string
  market_cap?: number
  price?: number
  price_date?: string
  price_change?: number
  price_change_pct?: number
  volume?: number
  pe_ratio?: number
  forward_pe?: number
  peg_ratio?: number
  pb_ratio?: number
  ps_ratio?: number
  roe?: number
  roa?: number
  gross_margin?: number
  operating_margin?: number
  net_margin?: number
  revenue_growth_yoy?: number
  earnings_growth_yoy?: number
  debt_equity?: number
  current_ratio?: number
  dividend_yield?: number
  payout_ratio?: number
  rsi_14?: number
  beta?: number
  sma_20?: number
  sma_50?: number
  sma_200?: number
  distance_52w_high?: number
  distance_52w_low?: number
}

export interface ScreenerRequest {
  filters: Filter[]
  sort?: SortConfig
  page: number
  page_size: number
  search?: string
}

export interface ScreenerResponse {
  total: number
  page: number
  page_size: number
  data: StockSummary[]
}

export interface CompanyInfo {
  ticker: string
  name: string
  sector?: string
  industry?: string
  exchange?: string
  market_cap?: number
  country?: string
  employees?: number
  description?: string
  website?: string
}

export interface Fundamentals {
  pe_ratio?: number
  forward_pe?: number
  peg_ratio?: number
  pb_ratio?: number
  ps_ratio?: number
  ev_ebitda?: number
  roe?: number
  roa?: number
  roic?: number
  gross_margin?: number
  operating_margin?: number
  net_margin?: number
  revenue_growth_yoy?: number
  revenue_growth_qoq?: number
  earnings_growth_yoy?: number
  debt_equity?: number
  current_ratio?: number
  quick_ratio?: number
  dividend_yield?: number
  payout_ratio?: number
}

export interface Technicals {
  sma_20?: number
  sma_50?: number
  sma_200?: number
  rsi_14?: number
  macd?: number
  beta?: number
  atr_14?: number
  distance_52w_high?: number
  distance_52w_low?: number
}

export interface PricePoint {
  date: string
  close: number
  volume: number
}

export interface StockDetail {
  company: CompanyInfo
  price?: number
  price_change?: number
  price_change_pct?: number
  fundamentals: Fundamentals
  technicals: Technicals
  price_history: PricePoint[]
}
