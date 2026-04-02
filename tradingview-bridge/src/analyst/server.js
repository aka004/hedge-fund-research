import express from 'express';
import cors from 'cors';
import {
  getChartState,
  getOhlcv,
  getIndicators,
  getIndicatorValues,
  getIndicatorGraphics,
} from '../cdp/chart-reader.js';
import { clearAllDrawings } from '../cdp/drawing-writer.js';
import { injectPanel, removePanel, isPanelInjected } from '../panel/inject.js';
import { buildSystemPrompt } from './prompt-builder.js';
import { conversation } from './conversation.js';
import { callClaude } from './claude-client.js';
import {
  parseDrawingInstructions,
  cleanResponseText,
  executeDrawings,
} from './drawing-parser.js';

const app = express();
app.use(cors());
app.use(express.json());

let cachedRegime = null;
let regimeFetchedAt = 0;
const REGIME_CACHE_TTL_MS = 60_000;

async function fetchMacroRegime() {
  const now = Date.now();
  if (cachedRegime !== null && (now - regimeFetchedAt) < REGIME_CACHE_TTL_MS) {
    return cachedRegime;
  }
  try {
    const resp = await fetch('http://localhost:8000/api/macro/indicators');
    if (resp.ok) {
      const data = await resp.json();
      cachedRegime = data.regime || null;
      regimeFetchedAt = now;
    }
  } catch {
    // Macro service unavailable — keep stale cache or null
  }
  return cachedRegime;
}

app.post('/api/analyze', async (req, res) => {
  try {
    const { message } = req.body;

    const [chartState, ohlcv, indicators, indValues, indGraphics, macroRegime] =
      await Promise.all([
        getChartState().catch(() => null),
        getOhlcv(50).catch(() => null),
        getIndicators().catch(() => null),
        getIndicatorValues().catch(() => []),
        getIndicatorGraphics().catch(() => []),
        fetchMacroRegime().catch(() => null),
      ]);

    const macroContext = macroRegime ? { regime: macroRegime } : null;
    const systemPrompt = buildSystemPrompt(
      chartState, ohlcv, indicators, macroContext, indValues, indGraphics
    );

    // Per-symbol conversation — auto-resets when chart context changes
    const symbol = chartState?.symbol || 'UNKNOWN';
    const resolution = chartState?.resolution || '60';
    const { messages, switched } = conversation.getHistory(symbol, resolution);

    if (switched) {
      console.log(`Chart switched to ${symbol}:${resolution} — new conversation`);
    }

    conversation.addMessage('user', message);

    const assistantText = await callClaude(systemPrompt, messages);
    conversation.addMessage('assistant', assistantText);

    const drawings = parseDrawingInstructions(assistantText);
    const drawingsExecuted = await executeDrawings(drawings);

    const regime = macroContext?.regime || cachedRegime || null;
    res.json({
      text: cleanResponseText(assistantText),
      drawings_executed: drawingsExecuted,
      chart: chartState,
      regime,
    });
  } catch (e) {
    console.error('Analyze error:', e);
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/clear-drawings', async (req, res) => {
  try {
    await clearAllDrawings();
    res.json({ success: true });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/status', async (req, res) => {
  const [state, regime] = await Promise.all([
    getChartState().catch(() => null),
    fetchMacroRegime(),
  ]);
  res.json({
    connected: !!state,
    chart: state,
    regime: regime || null,
  });
});

app.post('/api/reset', (req, res) => {
  conversation.resetAll();
  res.json({ success: true });
});

app.post('/api/panel/inject', async (req, res) => {
  try {
    await injectPanel();
    res.json({ success: true, message: 'AI panel injected' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.post('/api/panel/remove', async (req, res) => {
  try {
    await removePanel();
    res.json({ success: true, message: 'AI panel removed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

app.get('/api/panel/status', async (req, res) => {
  try {
    const injected = await isPanelInjected();
    res.json({ injected });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
});

export function startAnalystServer(port = 3456) {
  app.listen(port, () => {
    console.log(`Analyst server on http://localhost:${port}`);
  });
}
