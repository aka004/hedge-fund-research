export const PANEL_STYLES = `
  #tv-ai-panel {
    position: fixed;
    top: 0;
    right: 0;
    width: 320px;
    height: 100vh;
    background: #0a0a0a;
    border-left: 1px solid #1a1a1a;
    font-family: "SF Mono", "Cascadia Code", "Fira Code", "Consolas", monospace;
    font-size: 12px;
    color: #cccccc;
    display: flex;
    flex-direction: column;
    z-index: 999999;
    animation: tvai-slide-in 0.2s ease-out;
    box-sizing: border-box;
  }

  @keyframes tvai-slide-in {
    from { transform: translateX(320px); }
    to { transform: translateX(0); }
  }

  #tv-ai-panel * {
    box-sizing: border-box;
  }

  #tv-ai-panel .tvai-header {
    padding: 10px 12px;
    border-bottom: 1px solid #1a1a1a;
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

  #tv-ai-panel .tvai-badge-regime.bearish {
    background: #2a1a1a;
    border-color: #4a2a2a;
    color: #f87171;
  }

  #tv-ai-panel .tvai-badge-regime.neutral {
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
    background: #0a0a0a;
  }

  #tv-ai-panel .tvai-messages::-webkit-scrollbar-thumb {
    background: #333;
    border-radius: 2px;
  }

  #tv-ai-panel .tvai-msg {
    max-width: 90%;
    padding: 8px 10px;
    border-radius: 4px;
    line-height: 1.5;
    word-wrap: break-word;
    white-space: pre-wrap;
  }

  #tv-ai-panel .tvai-msg-ai {
    align-self: flex-start;
    background: #111;
    border: 1px solid #1a1a1a;
    color: #ff8c00;
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
    color: #666;
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
    border-top: 1px solid #1a1a1a;
    flex-shrink: 0;
  }

  #tv-ai-panel .tvai-action-btn {
    flex: 1;
    padding: 6px 4px;
    background: #111;
    border: 1px solid #1a1a1a;
    color: #999;
    font-family: inherit;
    font-size: 10px;
    cursor: pointer;
    border-radius: 2px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
  }

  #tv-ai-panel .tvai-action-btn:hover {
    background: #1a1a1a;
    color: #ff8c00;
    border-color: #ff8c00;
  }

  #tv-ai-panel .tvai-input-area {
    display: flex;
    gap: 6px;
    padding: 8px 12px 12px;
    border-top: 1px solid #1a1a1a;
    flex-shrink: 0;
  }

  #tv-ai-panel .tvai-input {
    flex: 1;
    background: #111;
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
  }

  #tv-ai-panel .tvai-input:focus {
    border-color: #ff8c00;
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
    color: #444;
    font-size: 11px;
    text-align: center;
    padding: 20px 10px;
    line-height: 1.6;
  }
`;
