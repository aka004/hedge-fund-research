# TradingView AI Integration — Design Spec

## Context

We want an AI-powered assistant that lives inside TradingView Desktop, can read chart data, hold conversations with the user via an injected sidebar, and draw annotations/overlays on charts. This connects to the existing hedge-fund-research macro dashboard for regime context.

Inspired by @Tradesdontlie's open-source TradingView-Claude bridge (Chrome DevTools Protocol approach). We'll study their implementation, then build a focused version tailored to our research workflow.

## Scope

This spec covers all 3 components as a single system, built incrementally:

1. **TradingView Bridge** — CDP connection, data extraction, drawing injection
2. **AI Chart Analyst** — Claude-powered analysis backend
3. **Chat Panel** — injected sidebar UI inside TradingView Desktop

---

## Component 1: TradingView Bridge (MCP Server)

### What It Does

Node.js server that connects to TradingView Desktop's Electron app via Chrome DevTools Protocol. Reads chart state and executes drawings.

### Connection

TradingView Desktop (Electron) exposes a CDP debugging port. The bridge connects via WebSocket:

```bash
# Launch TradingView Desktop with remote debugging enabled
# macOS: modify the app launch args or use the existing debug port
# Default Electron debug port: 9222

# Bridge connects to:
ws://localhost:9222/devtools/page/<pageId>
```

### Read Capabilities

| Data | CDP Method | Notes |
|------|-----------|-------|
| Current symbol & timeframe | `Runtime.evaluate` — query DOM/JS globals | TradingView exposes `window.TradingView` API internally |
| OHLC price data | `Runtime.evaluate` — access chart widget data model | Extract visible candles from the chart's internal data store |
| Visible indicators | `Runtime.evaluate` — enumerate loaded studies | Names, parameters, and plotted values |
| Pine Script source | `Runtime.evaluate` — read from Pine Editor DOM | Extract text from the Monaco/CodeMirror editor |
| Drawing objects | `Runtime.evaluate` — query drawing tool manager | Lines, rays, channels, rectangles, text notes |
| Screenshot | `Page.captureScreenshot` | For visual context when needed |

### Write Capabilities

#### Simple Drawings (CDP Drawing Tools)

Programmatically trigger TradingView's built-in drawing tools:

- **Horizontal lines** — support/resistance levels
- **Trendlines** — connecting two price points
- **Horizontal rays** — target levels
- **Text labels** — annotations at specific bar/price coordinates
- **Rectangles/boxes** — highlight zones (supply/demand, consolidation)

Method: `Runtime.evaluate` to call TradingView's internal drawing API, or `Input.dispatchMouseEvent` + `Input.dispatchKeyEvent` to simulate tool selection and placement.

#### Complex Overlays (Pine Script Injection)

For multi-layer analysis overlays:

1. Bridge writes Pine Script to a temp string
2. Injects into Pine Editor via CDP (`Runtime.evaluate` to set editor content)
3. Triggers compile via CDP (simulate click on "Add to Chart" or keyboard shortcut)
4. Reads compile errors back from the console/DOM

Use cases: custom indicator overlays, multi-timeframe analysis, pattern highlight scripts.

### MCP Server Interface

The bridge exposes MCP tools that the AI analyst (or Claude Code) can call:

```
Tools:
  tv_get_chart_state    → { symbol, timeframe, bars: [...], indicators: [...] }
  tv_get_drawings       → [{ type, points, color, text }]
  tv_get_pine_source    → string (current Pine Editor content)
  tv_draw_hline         → { price, color, label } → draws horizontal line
  tv_draw_trendline     → { point1, point2, color, label } → draws trendline
  tv_draw_label         → { bar, price, text, color } → places text label
  tv_draw_box           → { point1, point2, color, label } → draws rectangle
  tv_clear_drawings     → clears AI-created drawings (preserves user drawings)
  tv_inject_pine        → { code } → injects and compiles Pine Script
  tv_screenshot         → returns base64 PNG of current chart
```

### File Structure

```
tradingview-bridge/
├── package.json
├── src/
│   ├── index.ts              # MCP server entry point
│   ├── cdp/
│   │   ├── connection.ts     # CDP WebSocket connection manager
│   │   ├── chart-reader.ts   # Extract chart data (OHLC, indicators)
│   │   ├── drawing-writer.ts # Execute drawings via CDP
│   │   └── pine-injector.ts  # Pine Script editor interaction
│   ├── tools/
│   │   ├── chart-tools.ts    # MCP tool definitions for reading
│   │   ├── drawing-tools.ts  # MCP tool definitions for writing
│   │   └── pine-tools.ts     # MCP tool definitions for Pine Script
│   └── types.ts              # Shared type definitions
└── tsconfig.json
```

---

## Component 2: AI Chart Analyst (Backend)

### What It Does

Receives chart data + user questions, calls Claude API for analysis, returns text responses + drawing instructions. Optionally enriches context with macro regime data.

### Architecture

Lightweight Node.js (Express) or Python (FastAPI) server. Runs locally alongside the bridge.

**Decision: Node.js** — keeps the entire TradingView integration in one language/runtime with the bridge. Could even be the same process.

### Analysis Capabilities

#### Technical Analysis
- Pattern recognition: head & shoulders, double tops/bottoms, triangles, flags
- Support/resistance identification from price history
- Trendline detection and validation
- Moving average crossover analysis
- Volume profile interpretation

#### Macro Overlay
- Queries `http://localhost:8000/api/macro/indicators` for current regime
- Correlates chart movements with macro events (CPI releases, FOMC meetings)
- Contextualizes: "Price broke below 200MA while regime is HAWKISH — bearish confirmation"

#### Pine Script Assistant
- Writes Pine Script from natural language ("add a 20-period Bollinger Band with 2 std dev")
- Debugs compile errors — reads error output, fixes code, retries
- Explains existing Pine Script code
- Modifies indicators based on user requests

### API Endpoints

```
POST /api/analyze
  Body: { chart_state, user_message, conversation_history }
  Response: { text, drawings: [...], pine_script?: string }

POST /api/pine/generate
  Body: { description, existing_code? }
  Response: { code, explanation }

POST /api/pine/debug
  Body: { code, errors }
  Response: { fixed_code, explanation }
```

### Claude Prompt Structure

```
You are a senior technical analyst and Pine Script developer with access to a live TradingView chart.

Current chart:
- Symbol: {symbol} | Timeframe: {timeframe}
- Last {n} bars: {OHLC data}
- Active indicators: {list}
- Existing drawings: {list}

Macro context (from regime monitor):
- Regime: {HAWKISH/DOVISH/MIXED}
- Key indicators: {CPI, Fed Funds, etc.}

User question: {message}

Respond with:
1. Your analysis (concise, trader-style prose)
2. Drawing instructions (JSON array) for any annotations you want to place
3. Pine Script code if the user requested an indicator/strategy

Drawing instruction format:
[
  { "type": "hline", "price": 150.00, "color": "#ff3b30", "label": "Resistance" },
  { "type": "trendline", "from": { "bar": -20, "price": 145 }, "to": { "bar": 0, "price": 155 }, "color": "#00d26a" }
]
```

### Conversation Management

- Conversation history stored in memory per session (not persisted)
- Context window: last 10 messages + current chart state
- Each new symbol/timeframe change can optionally reset context
- Chart state is refreshed before every AI call (always current data)

### File Structure

```
tradingview-bridge/
├── src/
│   ├── analyst/
│   │   ├── server.ts         # Express server for /api/analyze etc.
│   │   ├── claude-client.ts  # Anthropic API wrapper
│   │   ├── prompt-builder.ts # Constructs prompts from chart data
│   │   ├── macro-context.ts  # Fetches from macro dashboard API
│   │   └── conversation.ts   # Manages chat history per session
```

---

## Component 3: Chat Panel (Injected UI)

### What It Does

A sidebar panel injected into TradingView Desktop via CDP. Provides a chat interface for the user to interact with the AI analyst.

### Injection Method

1. Bridge uses `Page.addScriptToEvaluateOnNewDocument` or `Runtime.evaluate` to inject a `<div>` container + CSS + JS into the TradingView page
2. The panel is a self-contained mini-app (vanilla JS + CSS, no build step needed since it's injected as a string)
3. Communicates with the analyst backend via `fetch()` to `localhost:<port>/api/analyze`

### UI Design

Bloomberg Terminal-style to match the macro dashboard aesthetic:

```
┌─────────────────────────────────────────────┬──────────────────┐
│                                             │  AI ANALYST      │
│                                             │  ────────────    │
│          TradingView Chart                  │  AAPL · 1D       │
│                                             │  Regime: HAWKISH │
│                                             │                  │
│                                             │  ┌─────────────┐ │
│                                             │  │ Chat msgs   │ │
│                                             │  │ ...         │ │
│                                             │  │ AI: I see a │ │
│                                             │  │ rising wedge│ │
│                                             │  └─────────────┘ │
│                                             │                  │
│                                             │  [Type message]  │
│                                             │  [Send]          │
└─────────────────────────────────────────────┴──────────────────┘
```

### Panel Features

- **Header**: Current symbol, timeframe, regime badge (from macro dashboard)
- **Chat area**: Scrollable message history, AI messages in amber, user messages in white
- **Input**: Text input with Enter-to-send, shift+Enter for newline
- **Quick actions**: Buttons for common requests:
  - "Analyze chart" — full technical analysis of current view
  - "Find levels" — identify support/resistance
  - "Write script" — open Pine Script assistant mode
  - "Clear drawings" — remove AI-placed annotations
- **Toggle**: Keyboard shortcut (e.g., `Ctrl+Shift+A`) to show/hide the panel
- **Resize**: Draggable left edge to adjust panel width

### Styling

- **Font**: JetBrains Mono (consistent with macro dashboard)
- **Background**: `#0a0a0a` with `#1a1a1a` borders
- **Colors**: Amber `#ff8c00` for AI text, white for user, red/green for signals
- **Width**: 300px default, resizable 200-500px
- **Position**: Right side, full height, overlays chart with slight transparency

### Panel Lifecycle

1. Bridge injects panel HTML/CSS/JS on startup
2. Panel fetches current chart state on load (shows symbol + timeframe)
3. Panel polls for chart state changes every 5s (updates header if symbol changes)
4. On user message: panel sends to analyst API → shows loading → displays response → bridge executes any drawings
5. Panel persists across TradingView page navigations via `Page.addScriptToEvaluateOnNewDocument`

### File Structure

```
tradingview-bridge/
├── src/
│   ├── panel/
│   │   ├── inject.ts         # CDP injection logic
│   │   ├── panel.html        # Panel HTML template (inlined as string)
│   │   ├── panel.css         # Panel styles (inlined)
│   │   └── panel.js          # Panel client-side logic (inlined)
```

---

## Integration Points

### With Macro Dashboard

The analyst backend makes an optional HTTP call to `localhost:8000/api/macro/indicators` to fetch:
- Current regime (HAWKISH / DOVISH / MIXED)
- Signal balance
- Key indicators (Fed Funds, CPI, unemployment)

This is injected into the Claude prompt as "Macro context" so the AI can reference it in analysis.

### With TradingView Bridge (from tweet)

Phase 1: Install and study @Tradesdontlie's bridge to understand:
- How they discover the CDP endpoint for TradingView Desktop
- Which `Runtime.evaluate` scripts extract chart data
- How Pine Script injection works
- What DOM selectors / internal APIs they use

Phase 2: Build our own slim version using the patterns learned, tailored to our needs.

---

## Build Order

| Phase | What | Deliverable |
|-------|------|-------------|
| 1 | Study existing bridge | Notes on CDP patterns, key scripts |
| 2 | Build bridge core | CDP connection + `tv_get_chart_state` + `tv_screenshot` |
| 3 | Add reading tools | All `tv_get_*` MCP tools working |
| 4 | Add drawing tools | `tv_draw_*` tools + `tv_inject_pine` |
| 5 | Build analyst backend | Express server + Claude API + prompt builder |
| 6 | Add macro context | Analyst queries macro dashboard API |
| 7 | Build chat panel | Injected sidebar with chat UI |
| 8 | Wire everything | End-to-end: user asks → AI analyzes → draws on chart |
| 9 | Polish | Quick action buttons, keyboard shortcuts, error handling |

---

## Technical Constraints

- **TradingView Desktop must be launched with remote debugging enabled** — user needs to configure this once (add `--remote-debugging-port=9222` to launch args)
- **CDP scripts are fragile** — TradingView updates may change internal APIs/DOM. We should isolate selectors/scripts so they're easy to update.
- **No TradingView server interaction** — everything is local, reads from the rendered app
- **TradingView ToS** — this is a personal tool for reading your own charts. No automation of trades, no data redistribution.
- **Rate limiting Claude API** — analyst should debounce rapid-fire requests, batch chart state reads

---

## Verification Plan

1. **Bridge**: Launch TradingView Desktop with debug port → bridge connects → `tv_get_chart_state` returns valid OHLC data
2. **Drawings**: Call `tv_draw_hline` → horizontal line appears on chart at correct price
3. **Pine Script**: Call `tv_inject_pine` with a simple SMA script → indicator appears on chart
4. **Analyst**: Send chart state + "analyze this chart" → Claude returns analysis + drawing instructions
5. **Macro context**: Analyst fetches from macro dashboard → regime data appears in AI response
6. **Chat Panel**: Panel visible in TradingView → type message → get AI response → drawings appear
7. **End-to-end**: Open AAPL daily chart → ask "find support and resistance levels" → AI identifies levels → horizontal lines drawn at correct prices
