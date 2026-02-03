"""
Stock detail API endpoint.
"""

import math
from fastapi import APIRouter, HTTPException
from ..models.schemas import StockDetail, CompanyInfo, Fundamentals, Technicals, PricePoint
from ..core.database import get_db

router = APIRouter(prefix="/api", tags=["stock"])


def clean_dict(data: dict) -> dict:
    """Replace NaN/Inf values with None for JSON serialization."""
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                cleaned[key] = None
            else:
                cleaned[key] = value
        else:
            cleaned[key] = value
    return cleaned


@router.get("/stock/{ticker}", response_model=StockDetail)
async def get_stock_detail(ticker: str):
    """
    Get detailed information for a single stock.
    
    Returns:
    - Company information
    - Latest fundamentals
    - Latest technicals
    - Price history (last 90 days)
    """
    
    ticker = ticker.upper()
    
    try:
        with get_db() as conn:
            # Get company info
            company_sql = """
            SELECT ticker, name, sector, industry, exchange, market_cap, 
                   country, employees, description, website
            FROM stocks
            WHERE ticker = $ticker
            """
            company_result = conn.execute(company_sql, {"ticker": ticker}).fetchdf()
            
            if len(company_result) == 0:
                raise HTTPException(status_code=404, detail=f"Stock {ticker} not found")
            
            company_data = clean_dict(company_result.to_dict('records')[0])
            company = CompanyInfo(**company_data)
            
            # Get latest price
            price_sql = """
            SELECT close, volume, date
            FROM prices
            WHERE ticker = $ticker
            ORDER BY date DESC
            LIMIT 1
            """
            price_result = conn.execute(price_sql, {"ticker": ticker}).fetchdf()
            
            current_price = None
            price_change = None
            price_change_pct = None
            
            if len(price_result) > 0:
                current_price = float(price_result['close'].iloc[0])
                
                # Get previous day's price for change calculation
                prev_price_sql = """
                SELECT close
                FROM prices
                WHERE ticker = $ticker
                ORDER BY date DESC
                LIMIT 2
                """
                prev_result = conn.execute(prev_price_sql, {"ticker": ticker}).fetchdf()
                
                if len(prev_result) == 2:
                    prev_price = float(prev_result['close'].iloc[1])
                    price_change = current_price - prev_price
                    price_change_pct = (price_change / prev_price) * 100
            
            # Get latest fundamentals
            fundamentals_sql = """
            SELECT pe_ratio, forward_pe, peg_ratio, pb_ratio, ps_ratio, ev_ebitda,
                   roe, roa, roic, gross_margin, operating_margin, net_margin,
                   revenue_growth_yoy, revenue_growth_qoq, earnings_growth_yoy,
                   debt_equity, current_ratio, quick_ratio, dividend_yield, payout_ratio
            FROM fundamentals
            WHERE ticker = $ticker
            ORDER BY period_end DESC
            LIMIT 1
            """
            fundamentals_result = conn.execute(fundamentals_sql, {"ticker": ticker}).fetchdf()
            
            fundamentals_data = {}
            if len(fundamentals_result) > 0:
                fundamentals_data = clean_dict(fundamentals_result.to_dict('records')[0])
            
            fundamentals = Fundamentals(**fundamentals_data)
            
            # Get latest technicals
            technicals_sql = """
            SELECT sma_20, sma_50, sma_200, rsi_14, macd, beta, atr_14,
                   distance_52w_high, distance_52w_low
            FROM technicals
            WHERE ticker = $ticker
            ORDER BY date DESC
            LIMIT 1
            """
            technicals_result = conn.execute(technicals_sql, {"ticker": ticker}).fetchdf()
            
            technicals_data = {}
            if len(technicals_result) > 0:
                technicals_data = clean_dict(technicals_result.to_dict('records')[0])
            
            technicals = Technicals(**technicals_data)
            
            # Get price history (last 90 days)
            history_sql = """
            SELECT date, close, volume
            FROM prices
            WHERE ticker = $ticker
            ORDER BY date DESC
            LIMIT 90
            """
            history_result = conn.execute(history_sql, {"ticker": ticker}).fetchdf()
            
            price_history = []
            if len(history_result) > 0:
                # Reverse to get chronological order
                history_result = history_result.sort_values('date')
                price_history = [
                    PricePoint(
                        date=row['date'],
                        close=float(row['close']),
                        volume=int(row['volume'])
                    )
                    for _, row in history_result.iterrows()
                ]
            
            return StockDetail(
                company=company,
                price=current_price,
                price_change=price_change,
                price_change_pct=price_change_pct,
                fundamentals=fundamentals,
                technicals=technicals,
                price_history=price_history
            )
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
