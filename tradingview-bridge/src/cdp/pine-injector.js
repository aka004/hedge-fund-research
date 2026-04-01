import { evaluate } from './connection.js';

export async function openPineEditor() {
  return evaluate(`(function() {
    try {
      window.TradingView.bottomWidgetBar.activateScriptEditorTab();
      return true;
    } catch(e) {
      var tab = document.querySelector('[aria-label="Pine"]')
        || document.querySelector('[data-name="pine-editor"]');
      if (tab) { tab.click(); return true; }
      return false;
    }
  })()`);
}

export async function findMonacoEditor() {
  return evaluate(`(function() {
    var container = document.querySelector('.monaco-editor.pine-editor-monaco');
    if (!container) return { found: false };
    var el = container;
    var fiberKey;
    for (var i = 0; i < 20; i++) {
      if (!el) break;
      fiberKey = Object.keys(el).find(function(k) {
        return k.startsWith('__reactFiber$');
      });
      if (fiberKey) break;
      el = el.parentElement;
    }
    if (!fiberKey) return { found: false, reason: 'no_fiber' };
    var current = el[fiberKey];
    for (var d = 0; d < 15; d++) {
      if (!current) break;
      if (current.memoizedProps
        && current.memoizedProps.value
        && current.memoizedProps.value.monacoEnv) {
        return { found: true };
      }
      current = current.return;
    }
    return { found: false, reason: 'no_monaco_env' };
  })()`);
}

export async function getPineSource() {
  return evaluate(`(function() {
    var container = document.querySelector('.monaco-editor.pine-editor-monaco');
    if (!container) return null;
    var el = container;
    var fiberKey;
    for (var i = 0; i < 20; i++) {
      if (!el) break;
      fiberKey = Object.keys(el).find(function(k) {
        return k.startsWith('__reactFiber$');
      });
      if (fiberKey) break;
      el = el.parentElement;
    }
    if (!fiberKey) return null;
    var current = el[fiberKey];
    for (var d = 0; d < 15; d++) {
      if (!current) break;
      if (current.memoizedProps
        && current.memoizedProps.value
        && current.memoizedProps.value.monacoEnv) {
        var env = current.memoizedProps.value.monacoEnv;
        var editors = env.editor.getEditors();
        if (editors.length > 0) return editors[0].getValue();
      }
      current = current.return;
    }
    return null;
  })()`);
}

export async function setPineSource(code) {
  const escaped = code
    .replace(/\\/g, '\\\\')
    .replace(/'/g, "\\'")
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '');
  return evaluate(`(function() {
    var container = document.querySelector('.monaco-editor.pine-editor-monaco');
    if (!container) return { success: false, reason: 'no_editor' };
    var el = container;
    var fiberKey;
    for (var i = 0; i < 20; i++) {
      if (!el) break;
      fiberKey = Object.keys(el).find(function(k) {
        return k.startsWith('__reactFiber$');
      });
      if (fiberKey) break;
      el = el.parentElement;
    }
    if (!fiberKey) return { success: false, reason: 'no_fiber' };
    var current = el[fiberKey];
    for (var d = 0; d < 15; d++) {
      if (!current) break;
      if (current.memoizedProps
        && current.memoizedProps.value
        && current.memoizedProps.value.monacoEnv) {
        var env = current.memoizedProps.value.monacoEnv;
        var editors = env.editor.getEditors();
        if (editors.length > 0) {
          editors[0].setValue('${escaped}');
          return { success: true };
        }
      }
      current = current.return;
    }
    return { success: false, reason: 'no_monaco_env' };
  })()`);
}

export async function compilePine() {
  return evaluate(`(function() {
    var btns = document.querySelectorAll('button');
    for (var i = 0; i < btns.length; i++) {
      var txt = btns[i].textContent.trim().toLowerCase();
      if (txt === 'add to chart'
        || txt === 'update on chart'
        || txt === 'save and add to chart'
        || txt === 'apply') {
        btns[i].click();
        return { success: true, action: txt };
      }
    }
    return { success: false, reason: 'no_compile_button' };
  })()`);
}

export async function getPineErrors() {
  return evaluate(`(function() {
    var container = document.querySelector('.monaco-editor.pine-editor-monaco');
    if (!container) return [];
    var el = container;
    var fiberKey;
    for (var i = 0; i < 20; i++) {
      if (!el) break;
      fiberKey = Object.keys(el).find(function(k) {
        return k.startsWith('__reactFiber$');
      });
      if (fiberKey) break;
      el = el.parentElement;
    }
    if (!fiberKey) return [];
    var current = el[fiberKey];
    for (var d = 0; d < 15; d++) {
      if (!current) break;
      if (current.memoizedProps
        && current.memoizedProps.value
        && current.memoizedProps.value.monacoEnv) {
        var env = current.memoizedProps.value.monacoEnv;
        var editors = env.editor.getEditors();
        if (editors.length > 0) {
          var model = editors[0].getModel();
          var markers = env.editor.getModelMarkers({ resource: model.uri });
          return markers.map(function(m) {
            return {
              line: m.startLineNumber,
              col: m.startColumn,
              message: m.message,
              severity: m.severity
            };
          });
        }
      }
      current = current.return;
    }
    return [];
  })()`);
}
