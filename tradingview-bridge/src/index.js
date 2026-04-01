import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema
} from '@modelcontextprotocol/sdk/types.js';

import {
  getConnectionStatus,
  screenshot
} from './cdp/connection.js';
import {
  getChartState,
  getOhlcv,
  getIndicators,
  getIndicatorValues,
  getDrawings,
  getVisibleRange
} from './cdp/chart-reader.js';
import {
  drawHorizontalLine,
  drawTrendline,
  drawLabel,
  drawBox,
  removeDrawing,
  clearAllDrawings
} from './cdp/drawing-writer.js';
import {
  getPineSource,
  setPineSource,
  compilePine,
  getPineErrors
} from './cdp/pine-injector.js';
import { startAnalystServer } from './analyst/server.js';

const TOOLS = [
  {
    name: 'tv_status',
    description: 'Check if TradingView is connected via Chrome DevTools Protocol. Returns connection status.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_chart_state',
    description: 'Get the current chart state including symbol ticker, timeframe/resolution, and chart type.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_ohlcv',
    description: 'Get OHLCV (Open, High, Low, Close, Volume) bar data from the active chart. Returns an array of price bars with timestamps.',
    inputSchema: {
      type: 'object',
      properties: {
        count: {
          type: 'number',
          description: 'Number of bars to retrieve (default: 100)',
          default: 100
        }
      }
    }
  },
  {
    name: 'tv_get_indicators',
    description: 'List all indicators/studies currently loaded on the chart (e.g., RSI, MACD, Moving Averages).',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_indicator_values',
    description: 'Get current indicator values from the data window. Returns the latest computed values for all active indicators.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_drawings',
    description: 'List all drawings/shapes on the chart (trendlines, horizontal lines, rectangles, labels, etc.).',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_visible_range',
    description: 'Get the currently visible time range on the chart (from/to timestamps).',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_pine_source',
    description: 'Get the current Pine Script source code from the Pine Editor. The editor must be open.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_draw_hline',
    description: 'Draw a horizontal line on the chart at a specific price level. Useful for marking support/resistance levels.',
    inputSchema: {
      type: 'object',
      properties: {
        price: { type: 'number', description: 'Price level for the horizontal line' },
        color: { type: 'string', description: 'Hex color (default: #ff8c00)', default: '#ff8c00' },
        label: { type: 'string', description: 'Text label for the line', default: '' }
      },
      required: ['price']
    }
  },
  {
    name: 'tv_draw_trendline',
    description: 'Draw a trendline between two points on the chart. Each point needs a Unix timestamp and price.',
    inputSchema: {
      type: 'object',
      properties: {
        point1: {
          type: 'object',
          description: 'Starting point {time: unix_timestamp, price: number}',
          properties: {
            time: { type: 'number' },
            price: { type: 'number' }
          },
          required: ['time', 'price']
        },
        point2: {
          type: 'object',
          description: 'Ending point {time: unix_timestamp, price: number}',
          properties: {
            time: { type: 'number' },
            price: { type: 'number' }
          },
          required: ['time', 'price']
        },
        color: { type: 'string', description: 'Hex color (default: #ff8c00)', default: '#ff8c00' },
        label: { type: 'string', description: 'Text label', default: '' }
      },
      required: ['point1', 'point2']
    }
  },
  {
    name: 'tv_draw_label',
    description: 'Draw a text label at a specific point on the chart.',
    inputSchema: {
      type: 'object',
      properties: {
        time: { type: 'number', description: 'Unix timestamp for label position' },
        price: { type: 'number', description: 'Price level for label position' },
        text: { type: 'string', description: 'Label text content' },
        color: { type: 'string', description: 'Hex color (default: #ff8c00)', default: '#ff8c00' }
      },
      required: ['time', 'price', 'text']
    }
  },
  {
    name: 'tv_draw_box',
    description: 'Draw a rectangle/box between two corner points on the chart. Useful for highlighting price zones.',
    inputSchema: {
      type: 'object',
      properties: {
        point1: {
          type: 'object',
          description: 'Top-left corner {time: unix_timestamp, price: number}',
          properties: {
            time: { type: 'number' },
            price: { type: 'number' }
          },
          required: ['time', 'price']
        },
        point2: {
          type: 'object',
          description: 'Bottom-right corner {time: unix_timestamp, price: number}',
          properties: {
            time: { type: 'number' },
            price: { type: 'number' }
          },
          required: ['time', 'price']
        },
        color: { type: 'string', description: 'Fill hex color with alpha (default: #ff8c0033)', default: '#ff8c0033' }
      },
      required: ['point1', 'point2']
    }
  },
  {
    name: 'tv_clear_drawings',
    description: 'Remove all drawings/shapes from the chart.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_remove_drawing',
    description: 'Remove a specific drawing by its entity ID.',
    inputSchema: {
      type: 'object',
      properties: {
        id: { type: 'string', description: 'The entity ID of the drawing to remove' }
      },
      required: ['id']
    }
  },
  {
    name: 'tv_inject_pine',
    description: 'Set/replace the Pine Script source code in the Pine Editor. Opens the editor if needed.',
    inputSchema: {
      type: 'object',
      properties: {
        code: { type: 'string', description: 'Pine Script source code to inject' }
      },
      required: ['code']
    }
  },
  {
    name: 'tv_compile_pine',
    description: 'Compile/apply the current Pine Script in the editor (clicks "Add to chart" or "Update on chart").',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_get_pine_errors',
    description: 'Get any Pine Script compilation errors/warnings from the editor.',
    inputSchema: { type: 'object', properties: {} }
  },
  {
    name: 'tv_screenshot',
    description: 'Capture a screenshot of the TradingView chart. Returns base64-encoded PNG image.',
    inputSchema: { type: 'object', properties: {} }
  }
];

async function handleToolCall(name, args) {
  switch (name) {
    case 'tv_status':
      return await getConnectionStatus();

    case 'tv_get_chart_state':
      return await getChartState();

    case 'tv_get_ohlcv':
      return await getOhlcv(args.count || 100);

    case 'tv_get_indicators':
      return await getIndicators();

    case 'tv_get_indicator_values':
      return await getIndicatorValues();

    case 'tv_get_drawings':
      return await getDrawings();

    case 'tv_get_visible_range':
      return await getVisibleRange();

    case 'tv_get_pine_source':
      return await getPineSource();

    case 'tv_draw_hline':
      return await drawHorizontalLine(
        args.price,
        args.color || '#ff8c00',
        args.label || ''
      );

    case 'tv_draw_trendline':
      return await drawTrendline(
        args.point1,
        args.point2,
        args.color || '#ff8c00',
        args.label || ''
      );

    case 'tv_draw_label':
      return await drawLabel(
        args.time,
        args.price,
        args.text,
        args.color || '#ff8c00'
      );

    case 'tv_draw_box':
      return await drawBox(
        args.point1,
        args.point2,
        args.color || '#ff8c0033'
      );

    case 'tv_clear_drawings':
      return await clearAllDrawings();

    case 'tv_remove_drawing':
      return await removeDrawing(args.id);

    case 'tv_inject_pine':
      return await setPineSource(args.code);

    case 'tv_compile_pine':
      return await compilePine();

    case 'tv_get_pine_errors':
      return await getPineErrors();

    case 'tv_screenshot': {
      const data = await screenshot();
      return { _type: 'image', data };
    }

    default:
      throw new Error(`Unknown tool: ${name}`);
  }
}

async function main() {
  const server = new Server(
    { name: 'tradingview-bridge', version: '1.0.0' },
    { capabilities: { tools: {} } }
  );

  server.setRequestHandler(ListToolsRequestSchema, async () => {
    return { tools: TOOLS };
  });

  server.setRequestHandler(CallToolRequestSchema, async (request) => {
    const { name, arguments: args } = request.params;
    try {
      const result = await handleToolCall(name, args || {});

      // Handle screenshot specially - return as image content
      if (result && result._type === 'image') {
        return {
          content: [
            {
              type: 'image',
              data: result.data,
              mimeType: 'image/png'
            }
          ]
        };
      }

      return {
        content: [
          {
            type: 'text',
            text: JSON.stringify(result, null, 2)
          }
        ]
      };
    } catch (e) {
      return {
        content: [
          {
            type: 'text',
            text: `Error: ${e.message}`
          }
        ],
        isError: true
      };
    }
  });

  // Start the analyst Express server alongside the MCP server
  startAnalystServer(parseInt(process.env.ANALYST_PORT || '3456', 10));

  // Connect MCP via stdio
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error('TradingView MCP Bridge running on stdio');
}

main().catch((e) => {
  console.error('Fatal error:', e);
  process.exit(1);
});
