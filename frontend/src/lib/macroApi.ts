const API_BASE = '/api'

async function get<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`)
  if (!response.ok) throw new Error(`API error: ${response.statusText}`)
  return response.json()
}

// Types
export interface IndicatorData {
  id: string
  name: string
  value: number | null
  display: string
  date: string
  prev_value: number | null
  trend: 'up' | 'down' | 'flat'
  trend_display: string
  signal: 'hawkish' | 'dovish' | 'neutral'
  series_id: string
  sparkline?: number[]
}

export interface IndicatorGroup {
  label: string
  color: string
  indicators: IndicatorData[]
}

export interface SignalBalance {
  hawkish: number
  dovish: number
  neutral: number
  total: number
  regime: 'HAWKISH' | 'DOVISH' | 'MIXED'
}

export interface MacroResponse {
  last_updated: string
  indicators: Record<string, IndicatorGroup>
  signal_balance: SignalBalance
}

export interface HistoryPoint {
  date: string
  value: number
}

export interface ReferenceLine {
  label: string
  value: number | null
  color: string
  dynamic?: boolean
}

export interface HistoryResponse {
  series_id: string
  name: string
  range: string
  data: HistoryPoint[]
  reference_lines: ReferenceLine[]
}

export interface VerdictResponse {
  generated_at: string
  regime: 'HAWKISH' | 'DOVISH' | 'MIXED'
  narrative: string
  signal_balance: SignalBalance
}

export const fetchMacroIndicators = (): Promise<MacroResponse> =>
  get('/macro/indicators')

export const fetchIndicatorHistory = (
  id: string,
  range: string = '2Y'
): Promise<HistoryResponse> =>
  get(`/macro/history/${id}?range=${range}`)

export const fetchMacroVerdict = (
  refresh = false
): Promise<VerdictResponse> =>
  get(`/macro/verdict${refresh ? '?refresh=true' : ''}`)
