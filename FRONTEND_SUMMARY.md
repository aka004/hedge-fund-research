# Stock Screener Frontend – Summary

## Current state

- **Screener:** Filters, search, sortable table, pagination, dark theme.
- **Stock detail:** Company info, fundamentals, technicals, price history; API NaN handling in `backend/app/api/stock.py` (`clean_dict()`).
- **Charts:** PriceChart (90-day + SMA 20/50/200) and RSIChart; Recharts rendering fixed via fixed-height wrapper and `isAnimationActive={false}`.
- **Watchlist:** Star column, localStorage persistence, “★ Watchlist” filter.
- **Filter presets:** Value, Growth, Momentum, Oversold one-click presets.
- **Export:** CSV export of current table (filters/sort) with timestamped filename.

## Key code

- `frontend/src/components/PriceChart.tsx`, `RSIChart.tsx` – charts
- `frontend/src/lib/watchlist.ts` – watchlist
- `frontend/src/lib/csvExport.ts` – CSV export
- `backend/app/api/stock.py` – stock detail API + NaN cleanup

## Optional next steps

- Change % column (if daily prior close available)
- Loading spinners, empty states, mobile polish
- Options IV smile (when data available)
