import type { VerdictResponse } from '../../lib/macroApi'

const REGIME_COLORS: Record<string, string> = {
  HAWKISH: '#ff3b30',
  DOVISH: '#00d26a',
  MIXED: '#ff8c00',
}

interface Props {
  verdict: VerdictResponse | null
  loading: boolean
}

/**
 * Highlights keywords in the narrative text.
 * Numbers with % are colored based on context words nearby.
 */
function highlightNarrative(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = []
  // Split on number patterns (e.g., 3.5%, $4.2T, 50bps)
  const regex = /(\d+\.?\d*[%]?(?:\s*(?:bps|bp))?|\$\d+\.?\d*[A-Z]?)/g
  let lastIndex = 0
  let match: RegExpExecArray | null

  while ((match = regex.exec(text)) !== null) {
    // Text before match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index))
    }

    // Determine color from surrounding context
    const before = text.slice(Math.max(0, match.index - 40), match.index).toLowerCase()
    let color = '#ff8c00' // default amber
    if (before.includes('down') || before.includes('fell') || before.includes('decline') || before.includes('below') || before.includes('weak')) {
      color = '#00d26a' // dovish/positive for markets
    } else if (before.includes('above') || before.includes('rose') || before.includes('surge') || before.includes('high') || before.includes('hot')) {
      color = '#ff3b30' // hawkish/concerning
    }

    parts.push(
      <span key={match.index} style={{ color, fontWeight: 600 }}>
        {match[0]}
      </span>
    )
    lastIndex = match.index + match[0].length
  }

  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex))
  }

  return parts
}

export function AIVerdict({ verdict, loading }: Props) {
  return (
    <div
      style={{
        background: '#0d0d0d',
        border: '1px solid #1a1a1a',
        borderLeft: '3px solid #ff8c00',
        borderRadius: '2px',
        padding: '16px',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '10px',
          marginBottom: '12px',
        }}
      >
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            fontWeight: 700,
            color: '#ff8c00',
            letterSpacing: '1px',
          }}
        >
          {'\u25B6'} AI BOTTOM LINE
        </span>
        <span
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '9px',
            color: '#0a0a0a',
            background: '#ff8c00',
            padding: '1px 6px',
            borderRadius: '2px',
            fontWeight: 700,
          }}
        >
          CLAUDE
        </span>
      </div>

      {loading ? (
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            color: '#555',
            padding: '20px 0',
          }}
        >
          <span style={{ animation: 'blink 1s infinite' }}>Generating verdict...</span>
        </div>
      ) : verdict ? (
        <>
          {/* Regime indicator */}
          <div style={{ marginBottom: '10px' }}>
            <span
              style={{
                fontFamily: "'JetBrains Mono', monospace",
                fontSize: '10px',
                color: REGIME_COLORS[verdict.regime] ?? '#888',
                fontWeight: 600,
              }}
            >
              REGIME: {verdict.regime}
            </span>
          </div>

          {/* Narrative */}
          <div
            style={{
              fontFamily: "'IBM Plex Mono', monospace",
              fontSize: '12px',
              lineHeight: 1.7,
              color: '#bbb',
              marginBottom: '12px',
            }}
          >
            {highlightNarrative(verdict.narrative)}
          </div>

          {/* Footer */}
          <div
            style={{
              fontFamily: "'JetBrains Mono', monospace",
              fontSize: '9px',
              color: '#444',
              borderTop: '1px solid #1a1a1a',
              paddingTop: '8px',
            }}
          >
            Generated {verdict.generated_at} | Source: FRED + Yahoo Finance
          </div>
        </>
      ) : (
        <div
          style={{
            fontFamily: "'JetBrains Mono', monospace",
            fontSize: '11px',
            color: '#555',
            padding: '20px 0',
          }}
        >
          Verdict unavailable
        </div>
      )}
    </div>
  )
}
