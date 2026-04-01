export const PANEL_STYLES = `
  #tv-ai-panel-container {
    position: fixed;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 999999;
    transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    pointer-events: none;
  }

  #tv-ai-panel-container.tvai-expanded {
    width: 280px;
    pointer-events: auto;
  }

  #tv-ai-panel-container.tvai-collapsed {
    width: 32px;
    pointer-events: auto;
  }

  #tv-ai-panel {
    position: absolute;
    top: 0;
    right: 0;
    width: 280px;
    height: 100%;
    background: rgba(10, 10, 10, 0.95);
    border-left: 1px solid rgba(255, 140, 0, 0.15);
    box-shadow: -2px 0 12px rgba(255, 140, 0, 0.05);
    font-family: "SF Mono", "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 12px;
    color: #cccccc;
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
    transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1),
                opacity 0.2s ease;
  }

  #tv-ai-panel-container.tvai-collapsed #tv-ai-panel {
    transform: translateX(280px);
    opacity: 0;
    pointer-events: none;
  }

  #tv-ai-panel-container.tvai-expanded #tv-ai-panel {
    transform: translateX(0);
    opacity: 1;
  }

  /* Collapse tab - visible when collapsed */
  #tvai-collapse-tab {
    position: absolute;
    top: 50%;
    left: 0;
    transform: translateY(-50%);
    width: 32px;
    height: 72px;
    background: rgba(10, 10, 10, 0.95);
    border: 1px solid rgba(255, 140, 0, 0.25);
    border-right: none;
    border-radius: 4px 0 0 4px;
    color: #ff8c00;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    writing-mode: vertical-rl;
    text-orientation: mixed;
    font-family: "SF Mono", "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 2px;
    transition: background 0.15s ease, border-color 0.15s ease;
    z-index: 1;
  }

  #tv-ai-panel-container.tvai-expanded #tvai-collapse-tab {
    left: -32px;
    border-right: none;
    border-radius: 4px 0 0 4px;
  }

  #tvai-collapse-tab:hover {
    background: rgba(255, 140, 0, 0.1);
    border-color: #ff8c00;
  }

  #tv-ai-panel * {
    box-sizing: border-box;
  }

  #tv-ai-panel .tvai-header {
    padding: 10px 12px;
    border-bottom: 1px solid rgba(255, 140, 0, 0.08);
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex-shrink: 0;
  }

  #tv-ai-panel .tvai-header-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  #tv-ai-panel .tvai-title {
    color: #ff8c00;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 1px;
  }

  #tv-ai-panel .tvai-shortcut {
    color: #555;
    font-size: 10px;
  }

  #tv-ai-panel .tvai-close-btn {
    background: none;
    border: 1px solid #333;
    color: #777;
    cursor: pointer;
    font-size: 14px;
    line-height: 1;
    padding: 2px 6px;
    font-family: inherit;
    border-radius: 2px;
  }

  #tv-ai-panel .tvai-close-btn:hover {
    color: #ff8c00;
    border-color: #ff8c00;
  }

  #tv-ai-panel .tvai-badges {
    display: flex;
    gap: 6px;
    align-items: center;
  }

  #tv-ai-panel .tvai-badge {
    padding: 2px 6px;
    border-radius: 2px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.5px;
  }

  #tv-ai-panel .tvai-badge-symbol {
    background: #1a1a1a;
    border: 1px solid #333;
    color: #fff;
  }

  #tv-ai-panel .tvai-badge-regime {
    background: #1a2a1a;
    border: 1px solid #2a4a2a;
    color: #4ade80;
  }

  #tv-ai-panel .tvai-badge-regime.hawkish {
    background: #2a1a1a;
    border-color: #4a2a2a;
    color: #f87171;
  }

  #tv-ai-panel .tvai-badge-regime.dovish {
    background: #1a2a1a;
    border-color: #2a4a2a;
    color: #4ade80;
  }

  #tv-ai-panel .tvai-badge-regime.mixed {
    background: #1a1a1a;
    border-color: #3a3a2a;
    color: #fbbf24;
  }

  #tv-ai-panel .tvai-messages {
    flex: 1;
    overflow-y: auto;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  #tv-ai-panel .tvai-messages::-webkit-scrollbar {
    width: 4px;
  }

  #tv-ai-panel .tvai-messages::-webkit-scrollbar-track {
    background: transparent;
  }

  #tv-ai-panel .tvai-messages::-webkit-scrollbar-thumb {
    background: #333;
    border-radius: 2px;
  }

  #tv-ai-panel .tvai-msg {
    max-width: 92%;
    padding: 8px 10px;
    border-radius: 4px;
    line-height: 1.5;
    word-wrap: break-word;
    white-space: pre-wrap;
  }

  #tv-ai-panel .tvai-msg-ai {
    align-self: flex-start;
    background: rgba(17, 17, 17, 0.9);
    border: 1px solid rgba(255, 140, 0, 0.1);
    color: #e0c090;
  }

  #tv-ai-panel .tvai-msg-user {
    align-self: flex-end;
    background: #1a1a1a;
    border: 1px solid #2a2a2a;
    color: #fff;
    text-align: right;
  }

  #tv-ai-panel .tvai-msg-time {
    font-size: 9px;
    color: #444;
    margin-top: 4px;
    display: block;
  }

  #tv-ai-panel .tvai-msg-drawings {
    font-size: 10px;
    color: #ff8c00;
    margin-top: 4px;
    display: block;
  }

  #tv-ai-panel .tvai-loading {
    align-self: flex-start;
    padding: 8px 10px;
    color: #ff8c00;
    font-size: 12px;
  }

  #tv-ai-panel .tvai-loading-dots span {
    animation: tvai-pulse 1.4s infinite;
    opacity: 0.3;
  }

  #tv-ai-panel .tvai-loading-dots span:nth-child(2) {
    animation-delay: 0.2s;
  }

  #tv-ai-panel .tvai-loading-dots span:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes tvai-pulse {
    0%, 80%, 100% { opacity: 0.3; }
    40% { opacity: 1; }
  }

  #tv-ai-panel .tvai-actions {
    display: flex;
    gap: 4px;
    padding: 8px 12px;
    border-top: 1px solid rgba(255, 140, 0, 0.08);
    flex-shrink: 0;
  }

  #tv-ai-panel .tvai-action-btn {
    flex: 1;
    padding: 6px 4px;
    background: rgba(17, 17, 17, 0.8);
    border: 1px solid #1a1a1a;
    color: #999;
    font-family: inherit;
    font-size: 10px;
    cursor: pointer;
    border-radius: 2px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    transition: all 0.15s ease;
  }

  #tv-ai-panel .tvai-action-btn:hover {
    background: rgba(255, 140, 0, 0.08);
    color: #ff8c00;
    border-color: rgba(255, 140, 0, 0.3);
  }

  #tv-ai-panel .tvai-input-area {
    display: flex;
    gap: 6px;
    padding: 8px 12px 12px;
    border-top: 1px solid rgba(255, 140, 0, 0.08);
    flex-shrink: 0;
  }

  #tv-ai-panel .tvai-input {
    flex: 1;
    background: rgba(17, 17, 17, 0.8);
    border: 1px solid #1a1a1a;
    color: #fff;
    font-family: inherit;
    font-size: 12px;
    padding: 8px 10px;
    border-radius: 2px;
    resize: none;
    outline: none;
    min-height: 36px;
    max-height: 80px;
    transition: border-color 0.15s ease;
  }

  #tv-ai-panel .tvai-input:focus {
    border-color: #ff8c00;
    box-shadow: 0 0 0 1px rgba(255, 140, 0, 0.15);
  }

  #tv-ai-panel .tvai-input::placeholder {
    color: #444;
  }

  #tv-ai-panel .tvai-send-btn {
    background: #ff8c00;
    border: none;
    color: #0a0a0a;
    font-family: inherit;
    font-size: 12px;
    font-weight: 700;
    padding: 8px 12px;
    cursor: pointer;
    border-radius: 2px;
    flex-shrink: 0;
    transition: background 0.15s ease;
  }

  #tv-ai-panel .tvai-send-btn:hover {
    background: #ffaa33;
  }

  #tv-ai-panel .tvai-send-btn:disabled {
    background: #333;
    color: #666;
    cursor: not-allowed;
  }

  #tv-ai-panel .tvai-welcome {
    color: #555;
    font-size: 11px;
    text-align: center;
    padding: 20px 10px;
    line-height: 1.6;
  }
`;
