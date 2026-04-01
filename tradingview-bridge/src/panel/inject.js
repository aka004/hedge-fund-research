import { evaluate } from '../cdp/connection.js';
import { PANEL_STYLES } from './panel-styles.js';
import { PANEL_SCRIPT } from './panel-script.js';

const PANEL_MARKUP = `
<div id="tvai-collapse-tab" title="Toggle AI Panel">AI</div>
<div id="tv-ai-panel">
  <div class="tvai-header">
    <div class="tvai-header-top">
      <span class="tvai-title">AI ANALYST</span>
      <span class="tvai-shortcut">Ctrl+Shift+A</span>
      <button class="tvai-close-btn" id="tvai-close-btn" title="Close panel">X</button>
    </div>
    <div class="tvai-badges">
      <span id="tvai-symbol" class="tvai-badge tvai-badge-symbol">---</span>
      <span id="tvai-regime" class="tvai-badge tvai-badge-regime mixed" style="display:none">---</span>
    </div>
  </div>

  <div id="tvai-messages" class="tvai-messages"></div>

  <div class="tvai-actions">
    <button class="tvai-action-btn" data-action="analyze">Analyze</button>
    <button class="tvai-action-btn" data-action="levels">Levels</button>
    <button class="tvai-action-btn" data-action="script">Script</button>
    <button class="tvai-action-btn" data-action="clear">Clear</button>
  </div>

  <div class="tvai-input-area">
    <textarea
      id="tvai-input"
      class="tvai-input"
      placeholder="Ask the AI analyst..."
      rows="1"
    ></textarea>
    <button id="tvai-send-btn" class="tvai-send-btn">SEND</button>
  </div>
</div>
`;

function escapeForEval(str) {
  return str
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '');
}

export async function injectPanel() {
  // Step 1: Remove existing panel
  await evaluate(`(function() {
    var existing = document.getElementById('tv-ai-panel-container');
    if (existing) existing.remove();
  })()`);

  // Step 2: Inject styles
  const escapedStyles = escapeForEval(PANEL_STYLES);
  await evaluate(`(function() {
    var style = document.createElement('style');
    style.id = 'tv-ai-panel-styles';
    style.textContent = '${escapedStyles}';
    document.head.appendChild(style);
  })()`);

  // Step 3: Inject HTML
  const escapedMarkup = escapeForEval(PANEL_MARKUP);
  await evaluate(`(function() {
    var container = document.createElement('div');
    container.id = 'tv-ai-panel-container';
    container.className = 'tvai-expanded';
    container.innerHTML = '${escapedMarkup}';
    document.body.appendChild(container);
  })()`);

  // Step 4: Inject script directly via evaluate (avoids escaping issues with script elements)
  await evaluate(PANEL_SCRIPT);

  // Step 5: Wire up event listeners via CDP
  await evaluate(`(function() {
    // Send button
    var sendBtn = document.getElementById('tvai-send-btn');
    if (sendBtn) sendBtn.addEventListener('click', function() { tvaiSend(); });

    // Close button
    var closeBtn = document.getElementById('tvai-close-btn');
    if (closeBtn) closeBtn.addEventListener('click', function() { tvaiClosePanel(); });

    // Collapse/expand tab
    var collapseTab = document.getElementById('tvai-collapse-tab');
    if (collapseTab) collapseTab.addEventListener('click', function() { tvaiTogglePanel(); });

    // Quick action buttons
    var actionBtns = document.querySelectorAll('.tvai-action-btn');
    for (var i = 0; i < actionBtns.length; i++) {
      (function(btn) {
        var action = btn.getAttribute('data-action');
        btn.addEventListener('click', function() { tvaiQuickAction(action); });
      })(actionBtns[i]);
    }

    // Input enter key
    var input = document.getElementById('tvai-input');
    if (input) {
      input.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          tvaiSend();
        }
      });
    }
  })()`);
}

export async function removePanel() {
  await evaluate(`(function() {
    var el = document.getElementById('tv-ai-panel-container');
    if (el) el.remove();
    var style = document.getElementById('tv-ai-panel-styles');
    if (style) style.remove();
    var script = document.getElementById('tv-ai-panel-script');
    if (script) script.remove();
  })()`);
}

export async function isPanelInjected() {
  return evaluate('!!document.getElementById("tv-ai-panel-container")');
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
