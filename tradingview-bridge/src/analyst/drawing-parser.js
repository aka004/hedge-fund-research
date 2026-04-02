import {
  drawHorizontalLine,
  drawTrendline,
  drawLabel,
  drawBox,
} from '../cdp/drawing-writer.js';

/**
 * Extract [DRAWINGS] JSON blocks from Claude's response text.
 */
export function parseDrawingInstructions(text) {
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

/**
 * Strip [DRAWINGS] blocks from Claude's response for clean display.
 */
export function cleanResponseText(text) {
  return text
    .replace(/```?\s*\[DRAWINGS\][\s\S]*?\[\/DRAWINGS\]\s*```?/g, '')
    .replace(/\[DRAWINGS\][\s\S]*?\[\/DRAWINGS\]/g, '')
    .trim();
}

/**
 * Execute parsed drawing instructions on the chart via CDP.
 * Returns count of successfully executed drawings.
 */
export async function executeDrawings(drawings) {
  let executed = 0;
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
      executed++;
    } catch (e) {
      console.error(`Drawing failed (${d.type}):`, e.message);
    }
  }
  return executed;
}
