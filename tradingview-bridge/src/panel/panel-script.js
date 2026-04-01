export const PANEL_SCRIPT = `
  var tvaiMessages = [];
  var tvaiLoading = false;
  var tvaiBaseUrl = 'http://localhost:3456';

  function tvaiTimestamp() {
    var d = new Date();
    var h = d.getHours().toString().padStart(2, '0');
    var m = d.getMinutes().toString().padStart(2, '0');
    var s = d.getSeconds().toString().padStart(2, '0');
    return h + ':' + m + ':' + s;
  }

  function tvaiScrollToBottom() {
    var container = document.getElementById('tvai-messages');
    if (container) {
      container.scrollTop = container.scrollHeight;
    }
  }

  function tvaiRenderMessages() {
    var container = document.getElementById('tvai-messages');
    if (!container) return;

    var html = '';

    if (tvaiMessages.length === 0) {
      html = '<div class="tvai-welcome">'
        + 'AI ANALYST READY<br>'
        + 'Ask a question or use quick actions below.'
        + '</div>';
    }

    for (var i = 0; i < tvaiMessages.length; i++) {
      var msg = tvaiMessages[i];
      var cls = msg.role === 'ai' ? 'tvai-msg tvai-msg-ai' : 'tvai-msg tvai-msg-user';
      html += '<div class="' + cls + '">';
      html += msg.text;
      if (msg.drawings > 0) {
        html += '<span class="tvai-msg-drawings">' + msg.drawings + ' drawing(s) applied</span>';
      }
      html += '<span class="tvai-msg-time">' + msg.time + '</span>';
      html += '</div>';
    }

    if (tvaiLoading) {
      html += '<div class="tvai-loading">'
        + '<span class="tvai-loading-dots">'
        + '<span>.</span><span>.</span><span>.</span>'
        + '</span> analyzing'
        + '</div>';
    }

    container.innerHTML = html;
    tvaiScrollToBottom();
  }

  function tvaiSend() {
    var input = document.getElementById('tvai-input');
    if (!input) return;
    var text = input.value.trim();
    if (!text || tvaiLoading) return;

    tvaiMessages.push({ role: 'user', text: text, time: tvaiTimestamp(), drawings: 0 });
    input.value = '';
    tvaiLoading = true;
    tvaiRenderMessages();

    var sendBtn = document.getElementById('tvai-send-btn');
    if (sendBtn) sendBtn.disabled = true;

    fetch(tvaiBaseUrl + '/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text })
    })
    .then(function(res) { return res.json(); })
    .then(function(data) {
      var response = data.response || data.text || data.message || 'No response.';
      var drawings = data.drawings_count || data.drawings || 0;
      tvaiMessages.push({ role: 'ai', text: response, time: tvaiTimestamp(), drawings: drawings });
    })
    .catch(function(err) {
      tvaiMessages.push({ role: 'ai', text: 'Error: ' + err.message, time: tvaiTimestamp(), drawings: 0 });
    })
    .finally(function() {
      tvaiLoading = false;
      if (sendBtn) sendBtn.disabled = false;
      tvaiRenderMessages();
    });
  }

  function tvaiQuickAction(type) {
    var input = document.getElementById('tvai-input');
    if (!input) return;

    if (type === 'clear') {
      fetch(tvaiBaseUrl + '/api/clear-drawings', { method: 'POST' })
        .then(function() {
          tvaiMessages.push({ role: 'ai', text: 'Drawings cleared.', time: tvaiTimestamp(), drawings: 0 });
          tvaiRenderMessages();
        })
        .catch(function(err) {
          tvaiMessages.push({ role: 'ai', text: 'Error clearing: ' + err.message, time: tvaiTimestamp(), drawings: 0 });
          tvaiRenderMessages();
        });
      return;
    }

    var prompts = {
      analyze: 'Analyze the current chart. Identify the trend, key patterns, and notable levels.',
      levels: 'Identify the key support and resistance levels on this chart.',
      script: 'Help me write a Pine Script indicator for this chart.'
    };

    if (prompts[type]) {
      input.value = prompts[type];
      tvaiSend();
    }
  }

  function tvaiPollStatus() {
    fetch(tvaiBaseUrl + '/api/status')
      .then(function(res) { return res.json(); })
      .then(function(data) {
        var symbolEl = document.getElementById('tvai-symbol');
        var regimeEl = document.getElementById('tvai-regime');
        if (symbolEl && data.symbol) {
          symbolEl.textContent = data.symbol;
        }
        if (regimeEl && data.regime) {
          regimeEl.textContent = data.regime.toUpperCase();
          regimeEl.className = 'tvai-badge tvai-badge-regime';
          if (data.regime.toLowerCase().indexOf('bear') !== -1) {
            regimeEl.className += ' bearish';
          } else if (data.regime.toLowerCase().indexOf('bull') !== -1) {
            // default green style
          } else {
            regimeEl.className += ' neutral';
          }
        }
      })
      .catch(function() {
        // silent fail on status poll
      });
  }

  function tvaiClosePanel() {
    var panel = document.getElementById('tv-ai-panel-container');
    if (panel) panel.remove();
  }

  // Initialize input handler
  var tvaiInput = document.getElementById('tvai-input');
  if (tvaiInput) {
    tvaiInput.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        tvaiSend();
      }
    });
  }

  // Initial render
  tvaiRenderMessages();

  // Poll status every 5 seconds
  tvaiPollStatus();
  setInterval(tvaiPollStatus, 5000);
`;
