import type {
  DashboardOverview,
  EquityCurveResponse,
  HoldingsResponse,
  FactorsResponse,
  FeatureImportanceResponse,
  CVPathsResponse,
  ValidationChecklistResponse,
  BootstrapComparisonResponse,
  RiskMetrics,
  HRPWeightsResponse,
  RegimeHistoryResponse,
  KellyPipelineResponse,
  RunsResponse,
} from '../types/dashboard'

const API_BASE = '/api'

function qs(runId?: string): string {
  return runId ? `?run_id=${runId}` : ''
}

async function get<T>(url: string): Promise<T> {
  const response = await fetch(`${API_BASE}${url}`)
  if (!response.ok) throw new Error(`API error: ${response.statusText}`)
  return response.json()
}

export async function fetchDashboardOverview(runId?: string): Promise<DashboardOverview> {
  return get(`/dashboard/overview${qs(runId)}`)
}

export async function fetchEquityCurve(runId?: string): Promise<EquityCurveResponse> {
  return get(`/dashboard/equity-curve${qs(runId)}`)
}

export async function fetchHoldings(runId?: string): Promise<HoldingsResponse> {
  return get(`/dashboard/holdings${qs(runId)}`)
}

export async function fetchFactors(): Promise<FactorsResponse> {
  return get('/dashboard/factors')
}

export async function fetchFeatureImportance(runId?: string): Promise<FeatureImportanceResponse> {
  return get(`/dashboard/feature-importance${qs(runId)}`)
}

export async function fetchCVPaths(runId?: string): Promise<CVPathsResponse> {
  return get(`/dashboard/cv-paths${qs(runId)}`)
}

export async function fetchValidationChecklist(runId?: string): Promise<ValidationChecklistResponse> {
  return get(`/dashboard/validation-checklist${qs(runId)}`)
}

export async function fetchBootstrapComparison(runId?: string): Promise<BootstrapComparisonResponse> {
  return get(`/dashboard/bootstrap-comparison${qs(runId)}`)
}

export async function fetchRiskMetrics(runId?: string): Promise<RiskMetrics> {
  return get(`/dashboard/risk-metrics${qs(runId)}`)
}

export async function fetchHRPWeights(runId?: string): Promise<HRPWeightsResponse> {
  return get(`/dashboard/hrp-weights${qs(runId)}`)
}

export async function fetchRegimeHistory(): Promise<RegimeHistoryResponse> {
  return get('/dashboard/regime-history')
}

export async function fetchKellyPipeline(ticker: string, runId?: string): Promise<KellyPipelineResponse> {
  const params = runId ? `?run_id=${runId}&ticker=${ticker}` : `?ticker=${ticker}`
  return get(`/dashboard/kelly-pipeline${params}`)
}

export async function fetchRuns(): Promise<RunsResponse> {
  return get('/dashboard/runs')
}
