import { evaluate } from './connection.js';

export async function getChartState() {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    return {
      symbol: chart.symbol(),
      resolution: chart.resolution(),
      chartType: chart.chartType()
    };
  })()`);
}

export async function getOhlcv(count = 100) {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    var bars = chart._chartWidget.model().mainSeries().bars();
    if (!bars || typeof bars.lastIndex !== 'function') return null;
    var result = [];
    var end = bars.lastIndex();
    var start = Math.max(bars.firstIndex(), end - ${count} + 1);
    for (var i = start; i <= end; i++) {
      var v = bars.valueAt(i);
      if (v) result.push({
        time: v[0], open: v[1], high: v[2],
        low: v[3], close: v[4], volume: v[5] || 0
      });
    }
    return {
      bars: result,
      total_bars: bars.size(),
      symbol: chart.symbol(),
      resolution: chart.resolution()
    };
  })()`);
}

export async function getIndicators() {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return [];
    var studies = chart.getAllStudies();
    return studies.map(function(s) {
      return { id: s.id, name: s.name };
    });
  })()`);
}

export async function getIndicatorValues() {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return [];
    var model = chart._chartWidget.model().model();
    var sources = model.dataSources();
    var results = [];
    for (var si = 0; si < sources.length; si++) {
      var s = sources[si];
      try {
        var dwv = s.dataWindowView();
        if (!dwv) continue;
        var items = dwv.items();
        var vals = [];
        for (var j = 0; j < items.length; j++) {
          if (items[j]._title && items[j]._value) {
            vals.push({ title: items[j]._title, value: items[j]._value });
          }
        }
        if (vals.length > 0) {
          results.push({
            name: s.title ? s.title() : 'unknown',
            values: vals
          });
        }
      } catch(e) {}
    }
    return results;
  })()`);
}

export async function getIndicatorGraphics() {
  return evaluate(`(function() {
    try {
      var chart = window.TradingViewApi._activeChartWidgetWV.value();
      if (!chart) return [];
      var model = chart._chartWidget.model().model();
      if (!model || typeof model.dataSources !== 'function') return [];
      var sources = model.dataSources();
      var results = [];

      function readCollection(pc, collName, key) {
        try {
          var coll = pc[collName];
          if (!coll || typeof coll.get !== 'function') return [];
          var sub = coll.get(key);
          if (!sub || typeof sub.get !== 'function') return [];
          var inner = sub.get(false);
          if (!inner || !inner._primitivesDataById) return [];
          var items = [];
          inner._primitivesDataById.forEach(function(v) { items.push(v); });
          return items;
        } catch(e) { return []; }
      }

      for (var si = 0; si < sources.length; si++) {
        var s = sources[si];
        try {
          var g = s._graphics;
          if (!g || !g._primitivesCollection) continue;
          var name = s.title ? s.title() : 'unknown';
          var pc = g._primitivesCollection;
          var graphics = { name: name, lines: [], labels: [], boxes: [] };

          var rawLines = readCollection(pc, 'dwglines', 'lines');
          for (var li = 0; li < rawLines.length; li++) {
            var v = rawLines[li];
            graphics.lines.push({ y1: v.y1, y2: v.y2, x1: v.x1, x2: v.x2, width: v.w, style: v.st });
          }

          var rawLabels = readCollection(pc, 'dwglabels', 'labels');
          for (var lbi = 0; lbi < rawLabels.length; lbi++) {
            var lv = rawLabels[lbi];
            graphics.labels.push({ text: lv.t || '', price: lv.y, time: lv.x });
          }

          var rawBoxes = readCollection(pc, 'dwgboxes', 'boxes');
          for (var bi = 0; bi < rawBoxes.length; bi++) {
            var bv = rawBoxes[bi];
            graphics.boxes.push({ y1: bv.y1, y2: bv.y2, x1: bv.x1, x2: bv.x2 });
          }

          var total = graphics.lines.length + graphics.labels.length + graphics.boxes.length;
          if (total > 0) results.push(graphics);
        } catch(e) {}
      }
      return results;
    } catch(e) {
      return [];
    }
  })()`);
}

export async function getDrawings() {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return [];
    var shapes = chart.getAllShapes();
    return shapes.map(function(s) {
      return { id: s.id, name: s.name };
    });
  })()`);
}

export async function getVisibleRange() {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    return chart.getVisibleRange();
  })()`);
}
