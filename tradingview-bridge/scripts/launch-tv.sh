#!/bin/bash
# Launch TradingView Desktop with Chrome DevTools Protocol enabled

# Kill existing TradingView
pkill -f TradingView 2>/dev/null
sleep 1

# Find TradingView
TV_PATH="/Applications/TradingView.app/Contents/MacOS/TradingView"
if [ ! -f "$TV_PATH" ]; then
  TV_PATH="$HOME/Applications/TradingView.app/Contents/MacOS/TradingView"
fi
if [ ! -f "$TV_PATH" ]; then
  echo "TradingView not found" && exit 1
fi

# Launch with debug port
CDP_PORT=${1:-9222}
"$TV_PATH" --remote-debugging-port=$CDP_PORT &
echo "TradingView launched with CDP on port $CDP_PORT"

# Wait for CDP
for i in $(seq 1 15); do
  if curl -s http://localhost:$CDP_PORT/json/version > /dev/null 2>&1; then
    echo "CDP ready"
    exit 0
  fi
  sleep 1
done
echo "CDP timeout" && exit 1
