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
  getIndicators,
  getIndicatorValues,
  getIndicatorGraphics
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

const RESOLUTION_LABELS = {
  '1': '1min', '3': '3min', '5': '5min', '15': '15min', '30': '30min',
  '45': '45min', '60': '1hr', '120': '2hr', '180': '3hr', '240': '4hr',
  'D': 'Daily', '1D': 'Daily', 'W': 'Weekly', '1W': 'Weekly',
  'M': 'Monthly', '1M': 'Monthly',
};

function buildSystemPrompt(chartState, ohlcv, indicators, macroContext, indicatorValues, indicatorGraphics) {
  const resolution = chartState?.resolution || '60';
  const tfLabel = RESOLUTION_LABELS[resolution] || resolution;

  let prompt = `You are a senior technical analyst and Pine Script developer with access to a live TradingView chart.

`;

  if (chartState) {
    prompt += `Current chart: ${chartState.symbol} | Timeframe: ${tfLabel}
`;
  }

  // Timeframe-aware guidance
  prompt += `
TIMEFRAME CONTEXT (${tfLabel}):
`;
  const resNum = parseInt(resolution) || 1440;
  if (resNum <= 15) {
    prompt += `- This is an INTRADAY scalping timeframe. Focus on micro-structure levels.
- Support/resistance should be very precise (within a few ticks).
- Only identify 2-3 key levels near the current price, not historical extremes.
- Levels should be spaced at least 0.1-0.3% apart.
`;
  } else if (resNum <= 240) {
    prompt += `- This is an INTRADAY swing timeframe. Focus on session-level structure.
- Identify levels from the current and recent sessions.
- Levels should be meaningful (tested multiple times, high volume).
- Keep to 3-5 key levels. Space them at least 0.5-1% apart.
`;
  } else {
    prompt += `- This is a POSITIONAL/SWING timeframe. Focus on major structural levels.
- Identify levels that have held over weeks/months.
- These should be significant zones, not minor intraday noise.
- Keep to 3-5 key levels. Space them at least 1-3% apart.
`;
  }

  if (ohlcv && ohlcv.bars && ohlcv.bars.length > 0) {
    const bars = ohlcv.bars;
    const last = bars[bars.length - 1];
    const first = bars[0];
    const high = Math.max(...bars.map(b => b.high));
    const low = Math.min(...bars.map(b => b.low));
    const range = high - low;
    prompt += `Price range: ${low.toFixed(2)} - ${high.toFixed(2)} (range: ${range.toFixed(2)})
Current: O:${last.open} H:${last.high} L:${last.low} C:${last.close}
`;

    // Include compact OHLCV for last 10 bars
    const recent = bars.slice(-10);
    prompt += `Recent bars (last 10):\n`;
    for (const b of recent) {
      prompt += `  ${new Date(b.time * 1000).toISOString().slice(0, 16)} O:${b.open} H:${b.high} L:${b.low} C:${b.close} V:${b.volume}\n`;
    }
  }

  if (indicators && indicators.length > 0) {
    prompt += `Active indicators: ${indicators.map(i => i.name).join(', ')}
`;
  }

  // Indicator current values (from Data Window)
  if (indicatorValues && indicatorValues.length > 0) {
    prompt += `\nINDICATOR VALUES (current bar):\n`;
    for (const ind of indicatorValues) {
      prompt += `  ${ind.name}:\n`;
      for (const v of ind.values.slice(0, 10)) {
        prompt += `    ${v.title}: ${v.value}\n`;
      }
    }
  }

  // Indicator graphics (lines, labels, boxes drawn by Pine Script indicators)
  if (indicatorGraphics && indicatorGraphics.length > 0) {
    prompt += `\nINDICATOR GRAPHICS (drawn by active indicators):\n`;
    for (const g of indicatorGraphics) {
      prompt += `  ${g.name}:\n`;
      if (g.lines.length > 0) {
        prompt += `    Lines (${g.lines.length}): `;
        const sample = g.lines.slice(-5);
        prompt += sample.map(l => `y1:${l.y1?.toFixed?.(2) || l.y1} y2:${l.y2?.toFixed?.(2) || l.y2}`).join(', ');
        prompt += '\n';
      }
      if (g.labels.length > 0) {
        prompt += `    Labels (${g.labels.length}): `;
        const sample = g.labels.slice(-8);
        prompt += sample.map(l => `"${l.text}" @${l.price?.toFixed?.(2) || l.price}`).join(', ');
        prompt += '\n';
      }
      if (g.boxes.length > 0) {
        prompt += `    Boxes (${g.boxes.length}): `;
        const sample = g.boxes.slice(-5);
        prompt += sample.map(b => `[${b.y1?.toFixed?.(2) || b.y1}-${b.y2?.toFixed?.(2) || b.y2}]`).join(', ');
        prompt += '\n';
      }
    }
    prompt += `\nYou can SEE the indicator graphics above. Use them in your analysis — reference the levels, signals, and zones they show.\n`;
  }

  if (macroContext) {
    const regime = macroContext.regime || 'UNKNOWN';
    prompt += `Macro regime: ${regime}
`;
  }

  prompt += `
DRAWING RULES:
- Only draw levels that are clearly visible and significant on the CURRENT timeframe.
- Do NOT cluster lines — ensure each level is meaningfully separated from the others.
- Use red (#ff3b30) for resistance, green (#00d26a) for support, amber (#ff8c00) for key pivots.
- Maximum 5 drawings per response.
- Label each line clearly (e.g., "Support $582", "Resistance $595").

When you want to draw on the chart, include a JSON block:
\`\`\`
[DRAWINGS]
[{"type":"hline","price":150.00,"color":"#ff3b30","label":"Resistance $150"}]
[/DRAWINGS]
\`\`\`

Drawing types:
- hline: {"type":"hline","price":NUMBER,"color":"#hex","label":"text"}
- trendline: {"type":"trendline","from":{"time":UNIX,"price":NUM},"to":{"time":UNIX,"price":NUM},"color":"#hex","label":"text"}
- label: {"type":"label","time":UNIX,"price":NUM,"text":"text","color":"#hex"}
- box: {"type":"box","from":{"time":UNIX,"price":NUM},"to":{"time":UNIX,"price":NUM},"color":"#hex"}

Keep analysis concise and trader-focused. Reference specific price levels.`;

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

    // 1. Get current chart context (including indicator values and graphics)
    const [chartState, ohlcv, indicators, indValues, indGraphics] = await Promise.all([
      getChartState().catch(() => null),
      getOhlcv(50).catch(() => null),
      getIndicators().catch(() => null),
      getIndicatorValues().catch(() => []),
      getIndicatorGraphics().catch(() => [])
    ]);

    // 2. Optionally get macro context
    let macroContext = null;
    try {
      const resp = await fetch('http://localhost:8000/api/macro/indicators');
      if (resp.ok) macroContext = await resp.json();
    } catch {}

    // 3. Build prompt with full indicator data
    const systemPrompt = buildSystemPrompt(
      chartState, ohlcv, indicators, macroContext, indValues, indGraphics
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
