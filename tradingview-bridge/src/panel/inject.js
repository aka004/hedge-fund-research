import { evaluate } from '../cdp/connection.js';
import { PANEL_HTML } from './panel-html.js';

export async function injectPanel() {
  const escaped = PANEL_HTML
    .replace(/\\/g, '\\\\')
    .replace(/`/g, '\\`')
    .replace(/\$/g, '\\$');

  await evaluate(`(function() {
    var existing = document.getElementById('tv-ai-panel-container');
    if (existing) existing.remove();

    var container = document.createElement('div');
    container.id = 'tv-ai-panel-container';
    container.innerHTML = \`${escaped}\`;
    document.body.appendChild(container);

    var scripts = container.querySelectorAll('script');
    for (var i = 0; i < scripts.length; i++) {
      var s = document.createElement('script');
      s.textContent = scripts[i].textContent;
      document.body.appendChild(s);
      scripts[i].remove();
    }
  })()`);
}

export async function removePanel() {
  await evaluate(`(function() {
    var el = document.getElementById('tv-ai-panel-container');
    if (el) el.remove();
  })()`);
}

export async function isPanelInjected() {
  return evaluate(`!!document.getElementById('tv-ai-panel-container')`);
}

export async function togglePanel() {
  var injected = await isPanelInjected();
  if (injected) {
    await removePanel();
  } else {
    await injectPanel();
  }
  return !injected;
}
