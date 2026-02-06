// Dashboard types matching backend Pydantic models (dashboard_schemas.py)

export interface DashboardOverview {
  run_id: string
  strategy_name: string
  nav: number
  total_pnl: number
  total_pnl_pct: number
  sharpe_raw: number
  psr: number
  deflated_sharpe: number
  max_drawdown: number
  current_drawdown: number
  win_rate: number
  regime: 'bull' | 'bear' | 'neutral'
  created_at: string
  is_mock: boolean
}

export interface EquityPoint {
  date: string
  equity: number
  benchmark_equity: number
  drawdown: number
  daily_return: number
}

export interface EquityCurveResponse {
  run_id: string
  data: EquityPoint[]
  is_mock: boolean
}

export interface Holding {
  ticker: string
  weight: number
  hrp_weight: number
  kelly_fraction: number
  signal_source: string
  pnl: number | null
  pnl_pct: number | null
  meta_prob: number | null
  is_mock: boolean
}

export interface HoldingsResponse {
  run_id: string
  date: string
  holdings: Holding[]
  is_mock: boolean
}

export interface DiscoveredFactor {
  id: number
  formula: string
  psr: number
  sharpe: number
  max_dd: number
  trades: number
  status: 'active' | 'monitoring' | 'rejected'
  is_mock: boolean
}

export interface FactorsResponse {
  factors: DiscoveredFactor[]
  is_mock: boolean
}

export interface FeatureImportance {
  feature_name: string
  importance: number
  is_mock: boolean
}

export interface FeatureImportanceResponse {
  run_id: string
  features: FeatureImportance[]
  is_mock: boolean
}

export interface CVPath {
  path_id: number
  equity_curve: number[]
}

export interface CVPathsResponse {
  run_id: string
  n_paths: number
  pbo: number
  paths: CVPath[]
  is_mock: boolean
}

export interface ValidationCheck {
  check: string
  passed: boolean
  detail: string | null
}

export interface ValidationChecklistResponse {
  run_id: string
  checks: ValidationCheck[]
  is_mock: boolean
}

export interface BootstrapComparison {
  method: string
  uniqueness: number
}

export interface BootstrapComparisonResponse {
  run_id: string
  comparisons: BootstrapComparison[]
  is_mock: boolean
}

export interface RiskMetrics {
  run_id: string
  sharpe: number
  sortino: number
  max_drawdown: number
  current_drawdown: number
  beta: number
  alpha: number
  calmar: number
  profit_factor: number
  win_rate: number
  turnover: number
  is_mock: boolean
}

export interface HRPWeightEntry {
  ticker: string
  hrp_weight: number
  actual_weight: number
}

export interface HRPWeightsResponse {
  run_id: string
  weights: HRPWeightEntry[]
  is_mock: boolean
}

export interface RegimePoint {
  date: string
  regime: string
  ma_200: number | null
  price: number | null
  distance_pct: number | null
  cusum_value: number | null
  days_in_regime: number | null
}

export interface RegimeHistoryResponse {
  data: RegimePoint[]
  is_mock: boolean
}

export interface KellySizingStep {
  step: string
  value: number
  ticker: string
}

export interface KellyPipelineResponse {
  run_id: string
  ticker: string
  steps: KellySizingStep[]
  is_mock: boolean
}

export interface RunSummary {
  run_id: string
  strategy_name: string
  created_at: string
  sharpe_raw: number
  psr: number
}

export interface RunsResponse {
  runs: RunSummary[]
}
