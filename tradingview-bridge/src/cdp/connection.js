import CDP from 'chrome-remote-interface';

const CDP_PORT = process.env.CDP_PORT || 9222;
const MAX_CONNECT_RETRIES = 2;
let client = null;

export async function findChartTarget() {
  const resp = await fetch(`http://localhost:${CDP_PORT}/json/list`);
  const targets = await resp.json();
  return targets.find(t => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url))
    || targets.find(t => t.type === 'page' && /tradingview/i.test(t.url))
    || null;
}

/**
 * Raw evaluate that does NOT reconnect — used for liveness checks
 * to avoid connect -> evaluate -> connect recursion.
 */
async function _evaluateRaw(expression) {
  if (!client) throw new Error('No CDP client');
  const result = await client.Runtime.evaluate({
    expression,
    returnByValue: true,
    awaitPromise: false
  });
  if (result.exceptionDetails) {
    const msg = result.exceptionDetails.exception?.description
      || result.exceptionDetails.text;
    throw new Error(`CDP eval error: ${msg}`);
  }
  return result.result?.value;
}

export async function connect(depth = 0) {
  if (depth > MAX_CONNECT_RETRIES) {
    throw new Error('CDP connection failed after max retries');
  }

  // Liveness check using raw evaluate (no reconnect loop)
  if (client) {
    try {
      await _evaluateRaw('1');
      return client;
    } catch {
      client = null;
    }
  }

  const target = await findChartTarget();
  if (!target) {
    throw new Error(
      'No TradingView chart tab found. Is TradingView running with --remote-debugging-port?'
    );
  }

  try {
    client = await CDP({ host: 'localhost', port: CDP_PORT, target: target.id });
    await client.Runtime.enable();
    await client.Page.enable();
    await client.DOM.enable();
    return client;
  } catch (e) {
    client = null;
    return connect(depth + 1);
  }
}

export async function evaluate(expression, awaitPromise = false) {
  const c = await connect();
  const result = await c.Runtime.evaluate({
    expression,
    returnByValue: true,
    awaitPromise
  });
  if (result.exceptionDetails) {
    const msg = result.exceptionDetails.exception?.description
      || result.exceptionDetails.text;
    throw new Error(`CDP eval error: ${msg}`);
  }
  return result.result?.value;
}

export async function screenshot(clip = null) {
  const c = await connect();
  const opts = { format: 'png' };
  if (clip) opts.clip = clip;
  const { data } = await c.Page.captureScreenshot(opts);
  return data; // base64
}

export async function getConnectionStatus() {
  try {
    const c = await connect();
    await _evaluateRaw('1');
    return { connected: true };
  } catch (e) {
    return { connected: false, error: e.message };
  }
}

export async function disconnect() {
  if (client) {
    await client.close();
    client = null;
  }
}
