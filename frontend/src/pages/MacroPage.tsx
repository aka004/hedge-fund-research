import { useState, useCallback, useEffect } from 'react'
import { useMacroData } from '../hooks/useMacroData'
import { IndicatorGroup } from '../components/macro/IndicatorGroup'
import { IndicatorChart } from '../components/macro/IndicatorChart'
import { SignalBalance } from '../components/macro/SignalBalance'
import { AIVerdict } from '../components/macro/AIVerdict'

const SIGNAL_COLORS: Record<string, string> = {
  hawkish: '#ff3b30',
  dovish: '#00d26a',
  neutral: '#888',
}

const GROUP_ORDER = ['fed_policy', 'inflation', 'employment', 'markets']

export function MacroPage() {
  const {
    indicators,
    verdict,
    history,
    loading,
    error,
    verdictLoading,
    historyLoading,
    loadHistory,
    clearHistory,
    refresh,
  } = useMacroData()

  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null)
  const [historyRange, setHistoryRange] = useState('2Y')

  const handleSelectIndicator = useCallback(
    (id: string) => {
      if (selectedId === id) {
        setSelectedId(null)
        setSelectedGroup(null)
        clearHistory()
        return
      }
      setSelectedId(id)
      setHistoryRange('2Y')
      loadHistory(id, '2Y')

      // Find which group this indicator belongs to
      if (indicators) {
        for (const [key, group] of Object.entries(indicators.indicators)) {
          if (group.indicators.some((ind) => ind.id === id)) {
            setSelectedGroup(key)
            break
          }
        }
      }
    },
    [selectedId, indicators, loadHistory, clearHistory]
  )

  const handleRangeChange = useCallback(
    (range: string) => {
      if (selectedId) {
        setHistoryRange(range)
        loadHistory(selectedId, range)
      }
    },
    [selectedId, loadHistory]
  )

  const handleCloseChart = useCallback(() => {
    setSelectedId(null)
    setSelectedGroup(null)
    clearHistory()
  }, [clearHistory])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return
      if (e.key === 'r' || e.key === 'R') refresh()
      if (e.key === 'Escape') handleCloseChart()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [refresh, handleCloseChart])

  // Find selected indicator's signal color for chart
  let chartColor = '#ff8c00'
  if (selectedId && indicators) {
    for (const group of Object.values(indicators.indicators)) {
      const ind = group.indicators.find((i) => i.id === selectedId)
      if (ind) {
        chartColor = SIGNAL_COLORS[ind.signal] ?? '#ff8c00'
        break
      }
    }
  }

  const now = new Date().toLocaleDateString('en-US', {
    weekday: 'short',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })

  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#0a0a0a',
        color: '#ccc',
        fontFamily: "'JetBrains Mono', monospace",
        position: 'relative',
      }}
    >
      {/* Scanline overlay */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          pointerEvents: 'none',
          zIndex: 9999,
          background:
            'repeating-linear-gradient(0deg, rgba(0,0,0,0.03) 0px, rgba(0,0,0,0.03) 1px, transparent 1px, transparent 2px)',
        }}
      />

      {/* Top bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '10px 20px',
          borderBottom: '1px solid #1a1a1a',
          background: '#0a0a0a',
          position: 'sticky',
          top: 0,
          zIndex: 100,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '14px', fontWeight: 700, color: '#ff8c00' }}>
            Macro Intelligence
          </span>
          <span style={{ fontSize: '10px', color: '#555', letterSpacing: '1px' }}>
            POLICY & MARKET REGIME MONITOR
          </span>
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: error ? '#ff3b30' : '#00d26a',
              boxShadow: `0 0 6px ${error ? '#ff3b3080' : '#00d26a80'}`,
              display: 'inline-block',
            }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ fontSize: '10px', color: '#555' }}>{now}</span>
          <span
            style={{
              fontSize: '11px',
              fontWeight: 700,
              color: '#ff8c00',
              background: '#1a1a00',
              padding: '2px 10px',
              border: '1px solid #ff8c0040',
              borderRadius: '2px',
            }}
          >
            MACRO &lt;GO&gt;
          </span>
        </div>
      </div>

      {/* Main content */}
      <div style={{ padding: '16px 20px' }}>
        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState error={error} onRetry={refresh} />
        ) : indicators ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '20px' }}>
            {/* Left panel: indicator groups */}
            <div>
              {GROUP_ORDER.map((key) => {
                const group = indicators.indicators[key]
                if (!group) return null
                return (
                  <div key={key}>
                    <IndicatorGroup
                      group={group}
                      groupKey={key}
                      onSelectIndicator={handleSelectIndicator}
                    />
                    {/* Chart appears below this group if selected indicator is in it */}
                    {selectedGroup === key && history && (
                      <IndicatorChart
                        history={history}
                        loading={historyLoading}
                        onRangeChange={handleRangeChange}
                        onClose={handleCloseChart}
                        lineColor={chartColor}
                      />
                    )}
                    {selectedGroup === key && !history && historyLoading && (
                      <IndicatorChart
                        history={{
                          series_id: '',
                          name: 'Loading...',
                          range: historyRange,
                          data: [],
                          reference_lines: [],
                        }}
                        loading={true}
                        onRangeChange={handleRangeChange}
                        onClose={handleCloseChart}
                        lineColor={chartColor}
                      />
                    )}
                  </div>
                )
              })}
            </div>

            {/* Right panel */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <SignalBalance balance={indicators.signal_balance} />
              <AIVerdict verdict={verdict} loading={verdictLoading} />
            </div>
          </div>
        ) : null}
      </div>

      {/* Footer bar */}
      <div
        style={{
          position: 'fixed',
          bottom: 0,
          left: 0,
          right: 0,
          display: 'flex',
          gap: '24px',
          padding: '6px 20px',
          borderTop: '1px solid #1a1a1a',
          background: '#0a0a0a',
          fontSize: '9px',
          color: '#444',
          zIndex: 100,
        }}
      >
        <span>
          <span style={{ color: '#ff8c00' }}>R</span> Refresh
        </span>
        <span>
          <span style={{ color: '#ff8c00' }}>H</span> History
        </span>
        <span>
          <span style={{ color: '#ff8c00' }}>E</span> Export
        </span>
        <span>
          <span style={{ color: '#ff8c00' }}>ESC</span> Close
        </span>
        <span style={{ marginLeft: 'auto' }}>
          {indicators?.last_updated ? `Updated: ${indicators.last_updated}` : ''}
        </span>
      </div>

      {/* Inline keyframe styles */}
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; max-height: 0; }
          to { opacity: 1; max-height: 400px; }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.3; }
        }
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50% { opacity: 1; }
        }
      `}</style>
    </div>
  )
}

function LoadingState() {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '60vh',
        gap: '16px',
      }}
    >
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '14px',
          color: '#ff8c00',
          animation: 'pulse 1.5s infinite',
        }}
      >
        LOADING MACRO DATA...
      </div>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '10px',
          color: '#444',
        }}
      >
        Fetching FRED indicators and market data
      </div>
    </div>
  )
}

function ErrorState({ error, onRetry }: { error: string; onRetry: () => void }) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '60vh',
        gap: '16px',
      }}
    >
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '14px',
          color: '#ff3b30',
        }}
      >
        CONNECTION ERROR
      </div>
      <div
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
          color: '#666',
          maxWidth: '400px',
          textAlign: 'center',
        }}
      >
        {error}
      </div>
      <button
        onClick={onRetry}
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '11px',
          color: '#ff8c00',
          background: 'transparent',
          border: '1px solid #ff8c00',
          padding: '6px 20px',
          cursor: 'pointer',
          borderRadius: '2px',
          marginTop: '8px',
        }}
      >
        RETRY
      </button>
    </div>
  )
}
