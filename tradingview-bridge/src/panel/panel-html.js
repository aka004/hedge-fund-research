import { PANEL_STYLES } from './panel-styles.js';
import { PANEL_SCRIPT } from './panel-script.js';

export const PANEL_HTML = `
<style>${PANEL_STYLES}</style>
<div id="tv-ai-panel">
  <div class="tvai-header">
    <div class="tvai-header-top">
      <span class="tvai-title">AI ANALYST</span>
      <span class="tvai-shortcut">Ctrl+Shift+A</span>
      <button class="tvai-close-btn" onclick="tvaiClosePanel()" title="Close panel">X</button>
    </div>
    <div class="tvai-badges">
      <span id="tvai-symbol" class="tvai-badge tvai-badge-symbol">---</span>
      <span id="tvai-regime" class="tvai-badge tvai-badge-regime neutral">---</span>
    </div>
  </div>

  <div id="tvai-messages" class="tvai-messages"></div>

  <div class="tvai-actions">
    <button class="tvai-action-btn" onclick="tvaiQuickAction('analyze')">Analyze</button>
    <button class="tvai-action-btn" onclick="tvaiQuickAction('levels')">Levels</button>
    <button class="tvai-action-btn" onclick="tvaiQuickAction('script')">Script</button>
    <button class="tvai-action-btn" onclick="tvaiQuickAction('clear')">Clear</button>
  </div>

  <div class="tvai-input-area">
    <textarea
      id="tvai-input"
      class="tvai-input"
      placeholder="Ask the AI analyst..."
      rows="1"
    ></textarea>
    <button id="tvai-send-btn" class="tvai-send-btn" onclick="tvaiSend()">SEND</button>
  </div>
</div>
<script>${PANEL_SCRIPT}</script>
`;
