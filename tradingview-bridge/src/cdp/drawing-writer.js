import { evaluate } from './connection.js';

export async function drawHorizontalLine(price, color = '#ff8c00', text = '') {
  const escapedText = text.replace(/'/g, "\\'");
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    var id = chart.createShape(
      { price: ${price} },
      {
        shape: 'horizontal_line',
        overrides: {
          linecolor: '${color}',
          linestyle: 0,
          linewidth: 2,
          showLabel: ${text ? 'true' : 'false'},
          text: '${escapedText}'
        }
      }
    );
    return { id: id, type: 'horizontal_line', price: ${price} };
  })()`);
}

export async function drawTrendline(point1, point2, color = '#ff8c00', text = '') {
  const escapedText = text.replace(/'/g, "\\'");
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    var id = chart.createMultipointShape(
      [
        { time: ${point1.time}, price: ${point1.price} },
        { time: ${point2.time}, price: ${point2.price} }
      ],
      {
        shape: 'trend_line',
        overrides: {
          linecolor: '${color}',
          linewidth: 2,
          text: '${escapedText}'
        }
      }
    );
    return { id: id, type: 'trend_line' };
  })()`);
}

export async function drawLabel(time, price, text, color = '#ff8c00') {
  const escapedText = text.replace(/'/g, "\\'");
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    var id = chart.createShape(
      { time: ${time}, price: ${price} },
      {
        shape: 'text',
        overrides: {
          color: '${color}',
          text: '${escapedText}'
        }
      }
    );
    return { id: id, type: 'text' };
  })()`);
}

export async function drawBox(point1, point2, color = '#ff8c0033', borderColor = '#ff8c00') {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return null;
    var id = chart.createMultipointShape(
      [
        { time: ${point1.time}, price: ${point1.price} },
        { time: ${point2.time}, price: ${point2.price} }
      ],
      {
        shape: 'rectangle',
        overrides: {
          color: '${color}',
          borderColor: '${borderColor}',
          borderWidth: 1
        }
      }
    );
    return { id: id, type: 'rectangle' };
  })()`);
}

export async function removeDrawing(entityId) {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return false;
    chart.removeEntity('${entityId}');
    return true;
  })()`);
}

export async function clearAllDrawings() {
  return evaluate(`(function() {
    var chart = window.TradingViewApi._activeChartWidgetWV.value();
    if (!chart) return false;
    chart.removeAllShapes();
    return true;
  })()`);
}
