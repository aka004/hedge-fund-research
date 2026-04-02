const RESOLUTION_LABELS = {
  '1': '1min', '3': '3min', '5': '5min', '15': '15min', '30': '30min',
  '45': '45min', '60': '1hr', '120': '2hr', '180': '3hr', '240': '4hr',
  'D': 'Daily', '1D': 'Daily', 'W': 'Weekly', '1W': 'Weekly',
  'M': 'Monthly', '1M': 'Monthly',
};

function formatTimeframeGuidance(resolution) {
  const resNum = parseInt(resolution) || 1440;
  if (resNum <= 15) {
    return `- This is an INTRADAY scalping timeframe. Focus on micro-structure levels.
- Support/resistance should be very precise (within a few ticks).
- Only identify 2-3 key levels near the current price, not historical extremes.
- Levels should be spaced at least 0.1-0.3% apart.`;
  } else if (resNum <= 240) {
    return `- This is an INTRADAY swing timeframe. Focus on session-level structure.
- Identify levels from the current and recent sessions.
- Levels should be meaningful (tested multiple times, high volume).
- Keep to 3-5 key levels. Space them at least 0.5-1% apart.`;
  }
  return `- This is a POSITIONAL/SWING timeframe. Focus on major structural levels.
- Identify levels that have held over weeks/months.
- These should be significant zones, not minor intraday noise.
- Keep to 3-5 key levels. Space them at least 1-3% apart.`;
}

function formatOhlcvSection(ohlcv) {
  if (!ohlcv?.bars?.length) return '';
  const bars = ohlcv.bars;
  const last = bars[bars.length - 1];
  const high = Math.max(...bars.map(b => b.high));
  const low = Math.min(...bars.map(b => b.low));
  const range = high - low;

  let section = `Price range: ${low.toFixed(2)} - ${high.toFixed(2)} (range: ${range.toFixed(2)})
Current: O:${last.open} H:${last.high} L:${last.low} C:${last.close}
Recent bars (last 10):\n`;

  for (const b of bars.slice(-10)) {
    section += `  ${new Date(b.time * 1000).toISOString().slice(0, 16)} O:${b.open} H:${b.high} L:${b.low} C:${b.close} V:${b.volume}\n`;
  }
  return section;
}

function formatIndicatorValues(indicatorValues) {
  if (!indicatorValues?.length) return '';
  let section = '\nINDICATOR VALUES (current bar):\n';
  for (const ind of indicatorValues) {
    section += `  ${ind.name}:\n`;
    for (const v of ind.values.slice(0, 10)) {
      section += `    ${v.title}: ${v.value}\n`;
    }
  }
  return section;
}

function formatIndicatorGraphics(indicatorGraphics) {
  if (!indicatorGraphics?.length) return '';
  let section = '\nINDICATOR GRAPHICS (drawn by active indicators):\n';
  for (const g of indicatorGraphics) {
    section += `  ${g.name}:\n`;
    if (g.lines.length > 0) {
      section += `    Lines (${g.lines.length}): `;
      section += g.lines.slice(-5).map(l =>
        `y1:${l.y1?.toFixed?.(2) || l.y1} y2:${l.y2?.toFixed?.(2) || l.y2}`
      ).join(', ');
      section += '\n';
    }
    if (g.labels.length > 0) {
      section += `    Labels (${g.labels.length}): `;
      section += g.labels.slice(-8).map(l =>
        `"${l.text}" @${l.price?.toFixed?.(2) || l.price}`
      ).join(', ');
      section += '\n';
    }
    if (g.boxes.length > 0) {
      section += `    Boxes (${g.boxes.length}): `;
      section += g.boxes.slice(-5).map(b =>
        `[${b.y1?.toFixed?.(2) || b.y1}-${b.y2?.toFixed?.(2) || b.y2}]`
      ).join(', ');
      section += '\n';
    }
  }
  section += '\nYou can SEE the indicator graphics above. Use them in your analysis — reference the levels, signals, and zones they show.\n';
  return section;
}

const DRAWING_RULES = `
DRAWING RULES:
- Only draw levels that are clearly visible and significant on the CURRENT timeframe.
- Do NOT cluster lines — ensure each level is meaningfully separated from the others.
- Use red (#ff3b30) for resistance, green (#00d26a) for support, amber (#ff8c00) for key pivots.
- Maximum 5 drawings per response.
- Label each line clearly (e.g., "Support $582", "Resistance $595").
- For trendlines and boxes, use Unix timestamps from the OHLCV bars provided above — do NOT guess timestamps.

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

export function buildSystemPrompt(chartState, ohlcv, indicators, macroContext, indicatorValues, indicatorGraphics) {
  const resolution = chartState?.resolution || '60';
  const tfLabel = RESOLUTION_LABELS[resolution] || resolution;

  let prompt = `You are a senior technical analyst and Pine Script developer with access to a live TradingView chart.\n\n`;

  if (chartState) {
    prompt += `Current chart: ${chartState.symbol} | Timeframe: ${tfLabel}\n`;
  }

  prompt += `\nTIMEFRAME CONTEXT (${tfLabel}):\n${formatTimeframeGuidance(resolution)}\n`;
  prompt += formatOhlcvSection(ohlcv);

  if (indicators?.length > 0) {
    prompt += `Active indicators: ${indicators.map(i => i.name).join(', ')}\n`;
  }

  prompt += formatIndicatorValues(indicatorValues);
  prompt += formatIndicatorGraphics(indicatorGraphics);

  if (macroContext) {
    prompt += `Macro regime: ${macroContext.regime || 'UNKNOWN'}\n`;
  }

  prompt += DRAWING_RULES;
  return prompt;
}

export { RESOLUTION_LABELS };
