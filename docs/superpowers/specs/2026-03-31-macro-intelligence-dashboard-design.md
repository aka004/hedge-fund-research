# Macro Intelligence Dashboard — Design Spec

## Context

We need a real-time macro regime monitor that aggregates key economic indicators, classifies each as hawkish/dovish/neutral, and provides an AI-generated regime verdict. This helps inform portfolio positioning by answering: "What regime are we in right now?"

Inspired by a Bloomberg-style macro dashboard, this adds a unique Fed excess reserves (net liquidity) indicator and an AI-powered narrative summary.

## Architecture

### Where It Lives

- **Frontend**: New `/macro` route in existing React app (`frontend/src/`)
- **Backend**: New `/api/macro` endpoints in FastAPI (`backend/app/api/`)
- **Data**: Cached in DuckDB (`data/cache/research.duckdb`) + Parquet for market data

### Data Flow

```
FRED API ──────────┐
                   ├──▶ FastAPI /api/macro/* ──▶ DuckDB cache ──▶ React /macro
Yahoo Finance ─────┘                                │
                                                     ▼
                                              Claude API (narrative)
```

---

## Indicators (15 total)

### Fed Policy (3)

| Indicator | Source | FRED Series | Signal Logic |
|-----------|--------|-------------|--------------|
| Fed Funds Rate | FRED | `DFF` | > 4.5% = hawk, < 2.5% = dove, else neutral. Rising = hawk bias. |
| Net Reserves | FRED | `WRESBAL` minus `RRPONTSYD` | Declining = hawk (tightening liquidity), rising = dove. Threshold: < $1T = hawk, > $2T = dove. |
| Deficit (CBO est) | Manual / FRED | `FYFSD` | > $1.5T = hawk (inflationary), < $500B = neutral. Rising = hawk bias. |

### Inflation (6)

| Indicator | Source | FRED Series | Signal Logic |
|-----------|--------|-------------|--------------|
| CPI YoY | FRED | `CPIAUCSL` (compute YoY) | > 3% = hawk, < 2% = dove, else neutral. Rising = hawk bias. |
| Core CPI YoY | FRED | `CPILFESL` (compute YoY) | > 3% = hawk, < 2% = dove, else neutral. Rising = hawk bias. |
| PPI YoY | FRED | `PPIACO` (compute YoY) | > 3% = hawk, < 1% = dove, else neutral. Rising = hawk bias. |
| Core PPI YoY | FRED | `WPSFD4131` (compute YoY) | > 3% = hawk, < 1% = dove, else neutral. Rising = hawk bias. |
| PCE YoY | FRED | `PCEPI` (compute YoY) | > 2.5% = hawk, < 1.5% = dove, else neutral. Rising = hawk bias. |
| Core PCE YoY | FRED | `PCEPILFE` (compute YoY) | > 2.5% = hawk, < 1.5% = dove, else neutral. Rising = hawk bias. |

### Employment (2)

| Indicator | Source | FRED Series | Signal Logic |
|-----------|--------|-------------|--------------|
| Unemployment Rate | FRED | `UNRATE` | > 4.5% = dove (weakness), < 3.5% = hawk (overheating), else neutral. Rising = dove bias. |
| Nonfarm Payrolls | FRED | `PAYEMS` (compute MoM change) | > +250K = hawk, < +100K = dove, else neutral. Declining trend = dove bias. |

### Markets & Commodities (4)

| Indicator | Source | Ticker/Series | Signal Logic |
|-----------|--------|---------------|--------------|
| S&P 500 | Yahoo | `^GSPC` | Above 200MA = dove (risk-on), below = hawk (risk-off). |
| Brent Crude | Yahoo | `BZ=F` | > $90 = hawk (inflationary), < $60 = dove, else neutral. Rising = hawk bias. |
| Sentiment (AAII) | FRED | `AAII` or manual | Bull% < 25 = dove (contrarian), > 45 = hawk (complacent). |
| VIX | Yahoo | `^VIX` | > 25 = dove (fear), < 15 = hawk (complacent), else neutral. |

> **Note**: Sentiment (AAII) may require manual entry or scraping if not available on FRED. Fallback: use VIX as sentiment proxy and drop AAII, keeping 14 indicators.

---

## Signal Classification Engine

Each indicator gets a signal via **level + trend** combined:

```python
def classify_signal(value, prev_value, thresholds):
    """
    thresholds = {
        'hawk_level': float,   # above this = hawkish
        'dove_level': float,   # below this = dovish
        'trend_weight': float  # how much trend shifts the signal (0.0-1.0)
    }
    """
    # Level score: -1 (dove) to +1 (hawk)
    level_score = compute_level_score(value, thresholds)

    # Trend score: rising = +1, falling = -1, flat = 0
    trend_score = compute_trend_score(value, prev_value)

    # Combined: weighted blend
    combined = (1 - trend_weight) * level_score + trend_weight * trend_score

    if combined > 0.3: return "hawkish"
    if combined < -0.3: return "dovish"
    return "neutral"
```

Thresholds are configurable per indicator (stored in a config dict, not hardcoded across the codebase).

---

## Historical Chart (Click-to-Expand)

Clicking any indicator card opens an expandable panel (or modal) showing:

1. **Line chart** of the indicator's historical values (from DuckDB cache)
2. **Selectable time range**: `1Y` | `2Y` | `5Y` | `MAX` buttons
3. **Context reference lines**:
   - CPI/PCE charts → Fed 2% target line
   - Unemployment → NAIRU estimate (~4.0%) line
   - S&P 500 → 200-day MA line
   - Fed Funds → neutral rate estimate (~2.5%) line
   - Net Reserves → pre-COVID level reference
4. **Release dots** — small markers on the x-axis showing when each data point was released
5. **Rendered with Recharts** (already in the project)

### Chart Interaction

- Click indicator card → a detail panel slides open below the indicator row (pushes content down)
- Chart loads from cached DuckDB data (zero API calls)
- Range buttons filter the cached dataset client-side
- Close button returns to the compact card view

---

## AI Bottom Line (Claude API)

### When It Runs

- On each data refresh (when any indicator updates)
- Cached alongside indicator data — not re-generated on every page load

### Prompt Structure

```
You are a macro strategist. Given the following indicator data:

{all_indicator_values_with_signals}

Signal balance: {hawk_count} hawkish, {dove_count} dovish, {neutral_count} neutral

Provide a 2-3 paragraph "Bottom Line" analysis covering:
1. The dominant macro theme right now
2. Key risks and what to watch
3. Overall regime classification (hawkish/dovish/mixed) and confidence level

Be specific — reference actual numbers. Write in Bloomberg-style prose: dense, direct, no filler.
```

### Output

- Narrative text (2-3 paragraphs)
- Regime verdict: `HAWKISH` | `DOVISH` | `MIXED` displayed as a badge
- Timestamp of when the analysis was generated

---

## Caching Strategy

### FRED Data (Economic Indicators)

- **First load**: Fetch full history per series (one call each, ~12 calls total)
- **Subsequent loads**: Check cache timestamp vs FRED release calendar
  - If cache is newer than last release → serve from DuckDB (0 calls)
  - If new release available → fetch only the latest data point (1 call)
- **Cache table**: `macro_indicators` in DuckDB

```sql
CREATE TABLE macro_indicators (
    series_id VARCHAR,      -- e.g., 'CPIAUCSL'
    date DATE,
    value DOUBLE,
    fetched_at TIMESTAMP,
    PRIMARY KEY (series_id, date)
);
```

### Yahoo Finance Data (Market Indicators)

- **Cache to Parquet** (existing pattern in `data/storage/parquet/`)
- **Refresh**: Once per day max (market data)
- **Historical**: Use existing `YahooFinanceProvider` class

### AI Narrative

- Cached in DuckDB alongside indicator data
- Re-generated only when underlying data changes

```sql
CREATE TABLE macro_ai_verdicts (
    id INTEGER PRIMARY KEY,
    generated_at TIMESTAMP,
    indicator_snapshot JSON,  -- the data used to generate
    narrative TEXT,
    regime VARCHAR,           -- HAWKISH / DOVISH / MIXED
    hawk_count INTEGER,
    dove_count INTEGER,
    neutral_count INTEGER
);
```

### API Call Budget

| Scenario | FRED Calls | Yahoo Calls | Claude Calls | Total |
|----------|-----------|-------------|--------------|-------|
| First ever load | ~12 | ~3 | 1 | ~16 |
| Page load (cached) | 0 | 0 | 0 | 0 |
| After monthly release | 1 | 0 | 1 | 2 |
| Daily market refresh | 0 | 3 | 0 | 3 |

FRED free tier: 120 req/min, 100K req/day. Well within limits.

---

## Backend API Endpoints

### `GET /api/macro/indicators`

Returns all current indicator values with signals.

```json
{
  "last_updated": "2026-03-31T09:41:00Z",
  "indicators": {
    "fed_policy": [
      {
        "id": "fed_funds",
        "name": "Fed Funds Rate",
        "value": 4.375,
        "display": "4.25-4.50%",
        "date": "2026-03-19",
        "prev_value": 4.375,
        "trend": "flat",
        "trend_display": "— HOLD",
        "signal": "hawkish",
        "series_id": "DFF"
      }
    ],
    "inflation": [...],
    "employment": [...],
    "markets": [...]
  },
  "signal_balance": {
    "hawkish": 7,
    "dovish": 4,
    "neutral": 4,
    "total": 15,
    "regime": "HAWKISH"
  }
}
```

### `GET /api/macro/history/{series_id}?range=2Y`

Returns historical data for a specific indicator.

```json
{
  "series_id": "CPIAUCSL",
  "name": "CPI YoY",
  "range": "2Y",
  "data": [
    {"date": "2024-04-01", "value": 3.4},
    {"date": "2024-05-01", "value": 3.3}
  ],
  "reference_lines": [
    {"label": "Fed Target", "value": 2.0, "color": "#ff8c00"}
  ]
}
```

### `GET /api/macro/verdict`

Returns the AI-generated narrative.

```json
{
  "generated_at": "2026-03-31T09:41:00Z",
  "regime": "HAWKISH",
  "narrative": "The macro picture is deteriorating...",
  "signal_balance": {"hawkish": 7, "dovish": 4, "neutral": 4}
}
```

---

## Frontend Components

```
frontend/src/
├── pages/
│   └── MacroPage.tsx              # Main page component, route: /macro
├── components/
│   └── macro/
│       ├── MacroTopBar.tsx         # Bloomberg-style header bar
│       ├── IndicatorCard.tsx       # Single indicator tile
│       ├── IndicatorGroup.tsx      # Section with header + row of cards
│       ├── IndicatorChart.tsx      # Expandable historical chart (Recharts)
│       ├── SignalBalance.tsx       # Donut chart + breakdown
│       ├── AIVerdict.tsx           # Bottom line narrative panel
│       └── MacroFooter.tsx         # Bottom bar with keyboard hints
├── hooks/
│   └── useMacroData.ts            # Data fetching + caching hook
└── lib/
    └── macroApi.ts                # API client for /api/macro/*
```

---

## Visual Design

- **Font**: JetBrains Mono (primary), IBM Plex Mono (data values)
- **Background**: `#0a0a0a` (near-black)
- **Card background**: `#0d0d0d` with `#1a1a1a` borders
- **Colors**: Amber `#ff8c00` (primary/policy), Red `#ff3b30` (hawkish), Green `#00d26a` (dovish), Gray `#888` (neutral), Blue `#0a84ff` (employment)
- **Section headers**: Colored labels with horizontal rule
- **Signal dots**: 6px circles with glow shadow on each card
- **Sparklines**: 8-bar mini charts on key indicators (CPI, unemployment, S&P, reserves)
- **Scanline overlay**: Subtle CRT effect via repeating-linear-gradient
- **Chart style**: Dark theme Recharts with grid lines at `#1a1a1a`, amber/red/green lines

---

## Files to Create/Modify

### New Files

| File | Purpose |
|------|---------|
| `backend/app/api/macro.py` | FastAPI router for `/api/macro/*` |
| `backend/app/services/macro_service.py` | Data fetching, caching, signal classification |
| `backend/app/services/macro_config.py` | Indicator definitions, thresholds, FRED series mapping |
| `frontend/src/pages/MacroPage.tsx` | Main page |
| `frontend/src/components/macro/MacroTopBar.tsx` | Header bar |
| `frontend/src/components/macro/IndicatorCard.tsx` | Indicator tile |
| `frontend/src/components/macro/IndicatorGroup.tsx` | Section grouping |
| `frontend/src/components/macro/IndicatorChart.tsx` | Historical chart |
| `frontend/src/components/macro/SignalBalance.tsx` | Donut + breakdown |
| `frontend/src/components/macro/AIVerdict.tsx` | AI narrative |
| `frontend/src/components/macro/MacroFooter.tsx` | Footer bar |
| `frontend/src/hooks/useMacroData.ts` | Data hook |
| `frontend/src/lib/macroApi.ts` | API client |

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Add `/macro` route |
| `backend/main.py` | Register `macro.router` |
| `config.py` | Add `FRED_API_KEY` getter if not present |

---

## Verification Plan

1. **Backend**: Start FastAPI, call `GET /api/macro/indicators` — verify real data from FRED/Yahoo with correct signals
2. **Cache**: Call endpoint twice — second call should be instant (0 API calls, served from DuckDB)
3. **History**: Call `GET /api/macro/history/CPIAUCSL?range=2Y` — verify 24 data points returned
4. **Frontend**: Navigate to `/macro` — verify all 15 indicator cards render with correct grouping
5. **Chart**: Click CPI card — verify historical chart opens with Fed 2% target line and range selector
6. **AI Verdict**: Verify narrative loads, references actual numbers, shows regime badge
7. **Signal Balance**: Verify donut chart matches individual card signals
8. **Staleness**: Wait 24h+ or manually expire cache — verify refresh fetches only stale series
