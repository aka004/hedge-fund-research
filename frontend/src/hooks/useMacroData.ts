import { useState, useEffect, useCallback } from 'react'
import {
  fetchMacroIndicators,
  fetchIndicatorHistory,
  fetchMacroVerdict,
  type MacroResponse,
  type HistoryResponse,
  type VerdictResponse,
} from '../lib/macroApi'

interface MacroDataState {
  indicators: MacroResponse | null
  verdict: VerdictResponse | null
  history: HistoryResponse | null
  loading: boolean
  error: string | null
  verdictLoading: boolean
  historyLoading: boolean
}

export function useMacroData() {
  const [state, setState] = useState<MacroDataState>({
    indicators: null,
    verdict: null,
    history: null,
    loading: true,
    error: null,
    verdictLoading: true,
    historyLoading: false,
  })

  const loadIndicators = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: null }))
    try {
      const data = await fetchMacroIndicators()
      setState((prev) => ({ ...prev, indicators: data, loading: false }))
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to load indicators'
      setState((prev) => ({ ...prev, error: msg, loading: false }))
    }
  }, [])

  const loadVerdict = useCallback(async (refresh = false) => {
    setState((prev) => ({ ...prev, verdictLoading: true }))
    try {
      const data = await fetchMacroVerdict(refresh)
      setState((prev) => ({ ...prev, verdict: data, verdictLoading: false }))
    } catch {
      setState((prev) => ({ ...prev, verdictLoading: false }))
    }
  }, [])

  const loadHistory = useCallback(async (id: string, range = '2Y') => {
    setState((prev) => ({ ...prev, historyLoading: true, history: null }))
    try {
      const data = await fetchIndicatorHistory(id, range)
      setState((prev) => ({ ...prev, history: data, historyLoading: false }))
    } catch {
      setState((prev) => ({ ...prev, historyLoading: false }))
    }
  }, [])

  const clearHistory = useCallback(() => {
    setState((prev) => ({ ...prev, history: null }))
  }, [])

  const refresh = useCallback(async () => {
    await Promise.all([loadIndicators(), loadVerdict(true)])
  }, [loadIndicators, loadVerdict])

  useEffect(() => {
    loadIndicators()
    loadVerdict()
  }, [loadIndicators, loadVerdict])

  return {
    ...state,
    loadHistory,
    clearHistory,
    refresh,
  }
}
