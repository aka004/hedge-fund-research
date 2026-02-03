# Stock Screener - Quick Start

**Status:** ✅ Phase 1 MVP Complete (Filter + Table + Detail Page)

---

## Running the Application

### Prerequisites
- Python 3.11+ (backend)
- Node.js 18+ (frontend)
- pnpm (recommended) or npm

### 1. Start Backend (Terminal 1)

```bash
cd ~/Documents/claude_code/claude-code-workspace/hedge-fund-research/backend

# Activate venv (if not already active)
source ../venv/bin/activate

# Run server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**API will be available at:** http://localhost:8000

**API Docs:** http://localhost:8000/docs

### 2. Start Frontend (Terminal 2)

```bash
cd ~/Documents/claude_code/claude-code-workspace/hedge-fund-research/frontend

# Install dependencies (first time only)
pnpm install

# Run dev server
pnpm dev
```

**Frontend will be available at:** http://localhost:5173

---

## Features Implemented

### ✅ Screener Page (`/screener`)
- **Filters:**
  - Sector (multi-select)
  - P/E Ratio (min/max)
  - Market Cap (minimum in billions)
  - RSI (14) (min/max)
- **Search:** Ticker or company name
- **Table:** 
  - Sortable columns (click header)
  - Shows: Ticker, Price, Change %, Market Cap, Volume, P/E, ROE, Gross Margin, Rev Growth, RSI
  - Click row to view details
- **Pagination:** 20 stocks per page

### ✅ Stock Detail Page (`/stock/:ticker`)
- Company header (ticker, name, exchange badge)
- Current price + change
- Quick stats grid (8 metrics)
- **Metrics sections:**
  - Valuation (P/E, P/B, P/S, EV/EBITDA)
  - Profitability (ROE, ROA, ROIC, margins)
  - Growth (revenue YoY/QoQ, earnings YoY)
  - Financial Health (debt/equity, current ratio)
  - Technical Indicators (SMA, RSI, MACD, beta)
  - Dividends (yield, payout ratio)
- Company info footer (sector, industry tags, description, website)

### ✅ Backend API
- `POST /api/screener` - Filter and search stocks
  - Supports operators: `eq`, `ne`, `lt`, `gt`, `lte`, `gte`, `between`, `in`, `contains`
  - Pagination + sorting
- `GET /api/stock/{ticker}` - Get stock details
  - Company info, fundamentals, technicals, 90-day price history
- `GET /health` - Health check

---

## Current Data Status

**Database:** `/Volumes/Data_2026/hedge-fund-research-data/research.duckdb`

**Tables:**
- `stocks` - 0 rows (company master)
- `prices` - 1,758 rows (historical prices)
- `fundamentals` - 0 rows (financial metrics)
- `technicals` - 0 rows (indicators)
- `options_chain` - 0 rows (options data)
- `signals` - 0 rows (trading signals)

⚠️ **Note:** Screener will return empty results until `stocks` table is populated.

---

## Next Steps

### Immediate (to test the screener)
1. **Populate `stocks` table** with S&P 500 tickers
2. **Fetch fundamentals** from Yahoo Finance for at least a few stocks
3. **Compute technicals** from price data

**Quick test script:**
```bash
cd ~/Documents/claude_code/claude-code-workspace/hedge-fund-research
source venv/bin/activate

# Populate sample stocks (you'll need to create this)
python scripts/populate_sample_stocks.py

# Fetch data for a few tickers
python scripts/fetch_data.py --ticker AAPL,MSFT,NVDA
```

### Phase 2 (Future)
- Price charts (Recharts integration)
- Options IV Smile visualization
- Filter presets (Value, Growth, Momentum, Oversold)
- Technical indicators on charts
- Watchlist feature
- Export to CSV

---

## Architecture

```
Frontend (React + TypeScript + Tailwind)
    │
    ↓ HTTP (proxied via Vite)
Backend (FastAPI)
    │
    ↓ DuckDB read-only connection
Database (DuckDB + Parquet)
    │
    ↓ Uses screener_summary view
Data Sources (Yahoo Finance, StockTwits)
```

**Key Design:**
- Frontend calls backend API (never talks to database directly)
- Backend uses `screener_summary` view (pre-joined, fast queries)
- DuckDB connection is read-only for safety
- All API params are validated via Pydantic

---

## Troubleshooting

### "No stocks match your filters"
- Check that `stocks` table is populated
- Check that `screener_summary` view returns data:
  ```bash
  duckdb /Volumes/Data_2026/hedge-fund-research-data/research.duckdb
  > SELECT COUNT(*) FROM screener_summary;
  ```

### CORS errors
- Ensure backend is running on port 8000
- Check Vite proxy config in `frontend/vite.config.ts`

### API 500 errors
- Check backend logs in Terminal 1
- Verify database path is correct in `config.py`

---

## Tech Stack

| Layer | Technology | Version |
|-------|------------|---------|
| Frontend Framework | React | 18.2 |
| Frontend Build | Vite | 5.0 |
| Frontend Language | TypeScript | 5.2 |
| Frontend Styling | Tailwind CSS | 3.4 |
| Backend Framework | FastAPI | 0.109 |
| Backend Server | Uvicorn | 0.27 |
| Database | DuckDB | 0.9 |
| Storage | Parquet | (via pyarrow 14.0) |
| Validation | Pydantic | 2.5 |

---

## File Structure

```
backend/
├── main.py                     # FastAPI app + CORS
├── app/
│   ├── api/
│   │   ├── screener.py         # POST /api/screener
│   │   └── stock.py            # GET /api/stock/{ticker}
│   ├── core/
│   │   └── database.py         # DuckDB connection manager
│   └── models/
│       └── schemas.py          # Pydantic request/response models

frontend/
├── src/
│   ├── components/
│   │   ├── ScreenerPage.tsx    # Main screener UI
│   │   ├── StockDetailPage.tsx # Stock detail UI
│   │   ├── FilterPanel.tsx     # Filter controls
│   │   └── StockTable.tsx      # Data table
│   ├── lib/
│   │   ├── api.ts              # API client
│   │   └── formatters.ts       # Number/currency formatting
│   └── types/
│       └── stock.ts            # TypeScript interfaces
```

---

**Built:** 2026-02-02  
**Time:** ~2 hours  
**Status:** Ready for data population and testing
