import { config } from 'dotenv';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

// Load .env from project root (hedge-fund-research/)
const __dirname = dirname(fileURLToPath(import.meta.url));
config({ path: resolve(__dirname, '../../..', '.env') });

import express from 'express';
import cors from 'cors';
import Anthropic from '@anthropic-ai/sdk';
import {
  getChartState,
  getOhlcv,
  getIndicators
} from '../cdp/chart-reader.js';
import {
  drawHorizontalLine,
  drawTrendline,
  drawLabel,
  drawBox,
  clearAllDrawings
} from '../cdp/drawing-writer.js';

const app = express();
app.use(cors());
app.use(express.json());

const anthropic = new Anthropic();

let conversationHistory = [];

// Cached macro regime — refreshed at most every 60 seconds
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

function buildSystemPrompt(chartState, ohlcv, indicators, macroContext) {
  let prompt = `You are a senior technical analyst and Pine Script developer with access to a live TradingView chart.

`;

  if (chartState) {
    prompt += `Current chart: ${chartState.symbol} | ${chartState.resolution}
`;
  }

  if (ohlcv && ohlcv.bars && ohlcv.bars.length > 0) {
    const bars = ohlcv.bars;
    const last = bars[bars.length - 1];
    const first = bars[0];
    prompt += `Last ${bars.length} bars: O:${first.open} -> C:${last.close} | H:${Math.max(...bars.map(b => b.high)).toFixed(2)} L:${Math.min(...bars.map(b => b.low)).toFixed(2)}
`;

    // Include compact OHLCV for last 10 bars
    const recent = bars.slice(-10);
    prompt += `Recent bars (last 10):\n`;
    for (const b of recent) {
      prompt += `  ${new Date(b.time * 1000).toISOString().slice(0, 10)} O:${b.open} H:${b.high} L:${b.low} C:${b.close} V:${b.volume}\n`;
    }
  }

  if (indicators && indicators.length > 0) {
    prompt += `Active indicators: ${indicators.map(i => i.name).join(', ')}
`;
  }

  if (macroContext) {
    const regime = macroContext.regime || 'UNKNOWN';
    prompt += `Macro regime: ${regime}
`;
  }

  prompt += `
When you want to draw on the chart, include a JSON block like:
\`\`\`
[DRAWINGS]
[{"type":"hline","price":150.00,"color":"#ff3b30","label":"Resistance"}]
[/DRAWINGS]
\`\`\`

Drawing types:
- hline: {"type":"hline","price":NUMBER,"color":"#hex","label":"text"}
- trendline: {"type":"trendline","from":{"time":UNIX,"price":NUM},"to":{"time":UNIX,"price":NUM},"color":"#hex","label":"text"}
- label: {"type":"label","time":UNIX,"price":NUM,"text":"text","color":"#hex"}
- box: {"type":"box","from":{"time":UNIX,"price":NUM},"to":{"time":UNIX,"price":NUM},"color":"#hex"}

Keep analysis concise and trader-focused. Reference specific price levels and patterns.`;

  return prompt;
}

function parseDrawingInstructions(text) {
  const drawings = [];
  const regex = /\[DRAWINGS\]\s*([\s\S]*?)\s*\[\/DRAWINGS\]/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    try {
      const parsed = JSON.parse(match[1]);
      if (Array.isArray(parsed)) {
        drawings.push(...parsed);
      } else {
        drawings.push(parsed);
      }
    } catch (e) {
      console.error('Failed to parse drawing instructions:', e.message);
    }
  }
  return drawings;
}

function cleanResponseText(text) {
  return text
    .replace(/```?\s*\[DRAWINGS\][\s\S]*?\[\/DRAWINGS\]\s*```?/g, '')
    .replace(/\[DRAWINGS\][\s\S]*?\[\/DRAWINGS\]/g, '')
    .trim();
}

app.post('/api/analyze', async (req, res) => {
  try {
    const { message } = req.body;

    // 1. Get current chart context
    const [chartState, ohlcv, indicators] = await Promise.all([
      getChartState().catch(() => null),
      getOhlcv(50).catch(() => null),
      getIndicators().catch(() => null)
    ]);

    // 2. Optionally get macro context
    let macroContext = null;
    try {
      const resp = await fetch('http://localhost:8000/api/macro/indicators');
      if (resp.ok) macroContext = await resp.json();
    } catch {}

    // 3. Build prompt
    const systemPrompt = buildSystemPrompt(
      chartState, ohlcv, indicators, macroContext
    );

    // 4. Add to conversation
    conversationHistory.push({ role: 'user', content: message });
    if (conversationHistory.length > 20) {
      conversationHistory = conversationHistory.slice(-20);
    }

    // 5. Call Claude
    const response = await anthropic.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 1500,
      system: systemPrompt,
      messages: conversationHistory
    });

    const assistantText = response.content[0].text;
    conversationHistory.push({ role: 'assistant', content: assistantText });

    // 6. Parse drawing instructions from response
    const drawings = parseDrawingInstructions(assistantText);

    // 7. Execute drawings
    for (const d of drawings) {
      try {
        if (d.type === 'hline') {
          await drawHorizontalLine(d.price, d.color, d.label);
        } else if (d.type === 'trendline') {
          await drawTrendline(d.from, d.to, d.color, d.label);
        } else if (d.type === 'label') {
          await drawLabel(d.time, d.price, d.text, d.color);
        } else if (d.type === 'box') {
          await drawBox(d.from, d.to, d.color);
        }
      } catch (e) {
        console.error('Drawing failed:', e);
      }
    }

    // 8. Return clean text with regime
    const regime = macroContext?.regime || cachedRegime || null;
    res.json({
      text: cleanResponseText(assistantText),
      drawings_executed: drawings.length,
      chart: chartState,
      regime
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
    fetchMacroRegime()
  ]);
  res.json({
    connected: !!state,
    chart: state,
    regime: regime || null
  });
});

app.post('/api/reset', (req, res) => {
  conversationHistory = [];
  res.json({ success: true });
});

export function startAnalystServer(port = 3456) {
  app.listen(port, () => {
    console.log(`Analyst server on http://localhost:${port}`);
  });
}
