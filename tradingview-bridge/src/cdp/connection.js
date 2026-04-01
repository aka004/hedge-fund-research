import CDP from 'chrome-remote-interface';

const CDP_PORT = process.env.CDP_PORT || 9222;
let client = null;

export async function findChartTarget() {
  const resp = await fetch(`http://localhost:${CDP_PORT}/json/list`);
  const targets = await resp.json();
  return targets.find(t => t.type === 'page' && /tradingview\.com\/chart/i.test(t.url))
    || targets.find(t => t.type === 'page' && /tradingview/i.test(t.url))
    || null;
}

export async function connect() {
  if (client) {
    try { await evaluate('1'); return client; } catch { client = null; }
  }
  const target = await findChartTarget();
  if (!target) {
    throw new Error(
      'No TradingView chart tab found. Is TradingView running with --remote-debugging-port?'
    );
  }
  client = await CDP({ host: 'localhost', port: CDP_PORT, target: target.id });
  await client.Runtime.enable();
  await client.Page.enable();
  await client.DOM.enable();
  return client;
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
    await evaluate('1');
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
