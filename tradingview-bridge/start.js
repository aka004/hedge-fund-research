/**
 * TradingView AI Bridge — Launcher
 *
 * Starts the analyst server and injects the chat panel into TradingView.
 * Run: node start.js
 *
 * Prerequisites:
 *   - TradingView Desktop running with: --remote-debugging-port=9222
 *   - ANTHROPIC_API_KEY in ../.env
 */

import { startAnalystServer } from './src/analyst/server.js';
import { injectPanel } from './src/panel/inject.js';
import { getConnectionStatus } from './src/cdp/connection.js';

const ANALYST_PORT = process.env.ANALYST_PORT || 3456;

async function main() {
  console.log('TradingView AI Bridge');
  console.log('─'.repeat(40));

  // 1. Check CDP connection
  console.log('Checking TradingView connection...');
  const status = await getConnectionStatus();
  if (!status.connected) {
    console.error('ERROR: Cannot connect to TradingView Desktop.');
    console.error('Make sure TradingView is running with:');
    console.error('  bash scripts/launch-tv.sh');
    process.exit(1);
  }
  console.log('Connected to TradingView');

  // 2. Start analyst server
  startAnalystServer(ANALYST_PORT);

  // 3. Wait a moment for server to be ready
  await new Promise(r => setTimeout(r, 1000));

  // 4. Inject panel
  console.log('Injecting AI panel...');
  await injectPanel();
  console.log('Panel injected');

  console.log('─'.repeat(40));
  console.log('Ready! Open TradingView to see the AI panel.');
  console.log('Press Ctrl+C to stop.');
}

main().catch(e => {
  console.error('Startup failed:', e.message);
  process.exit(1);
});
