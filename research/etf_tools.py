#!/usr/bin/env python3
"""
ETF-Specific Tools for Research Agents
=======================================

Tools for fetching ETF-specific data: structure, holdings, 
commodity prices, and macro data.
"""

import json
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import requests


def get_etf_info(ticker: str) -> Dict[str, Any]:
    """
    Get comprehensive ETF information including structure, 
    expense ratio, AUM, and performance.
    """
    try:
        etf = yf.Ticker(ticker)
        info = etf.info
        
        # Calculate premium/discount to NAV
        nav = info.get("navPrice", 0)
        price = info.get("regularMarketPrice", 0)
        premium_discount = ((price - nav) / nav * 100) if nav and price else None
        
        # Get historical performance
        hist = etf.history(period="1y")
        ytd_return = None
        if not hist.empty:
            ytd_start = datetime(datetime.now().year, 1, 1)
            ytd_data = hist[hist.index >= ytd_start.strftime("%Y-%m-%d")]
            if len(ytd_data) > 0:
                ytd_return = (ytd_data["Close"].iloc[-1] / ytd_data["Close"].iloc[0] - 1) * 100
        
        result = {
            "ticker": ticker,
            "name": info.get("longName") or info.get("shortName"),
            "category": info.get("category"),
            "fund_family": info.get("fundFamily"),
            "legal_type": info.get("legalType"),
            "expense_ratio_pct": info.get("netExpenseRatio"),
            "aum_billions": info.get("totalAssets", 0) / 1e9 if info.get("totalAssets") else None,
            "nav": nav,
            "price": price,
            "premium_discount_pct": premium_discount,
            "avg_volume": info.get("averageVolume"),
            "avg_volume_10d": info.get("averageVolume10days"),
            "bid_ask_spread": (info.get("ask", 0) - info.get("bid", 0)) if info.get("ask") and info.get("bid") else None,
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "50d_ma": info.get("fiftyDayAverage"),
            "200d_ma": info.get("twoHundredDayAverage"),
            "ytd_return_pct": ytd_return,
            "3y_return_pct": info.get("threeYearAverageReturn", 0) * 100 if info.get("threeYearAverageReturn") else None,
            "5y_return_pct": info.get("fiveYearAverageReturn", 0) * 100 if info.get("fiveYearAverageReturn") else None,
            "dividend_yield_pct": info.get("yield", 0) * 100 if info.get("yield") else None,
            "beta": info.get("beta3Year"),
            "inception_date": datetime.fromtimestamp(info.get("fundInceptionDate")).strftime("%Y-%m-%d") if info.get("fundInceptionDate") else None,
            "description": info.get("longBusinessSummary"),
        }
        
        return {"status": "success", "data": result}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_commodity_price(commodity: str) -> Dict[str, Any]:
    """
    Get current price and historical data for a commodity.
    
    Supported: gold, silver, oil, natural_gas, copper, platinum, palladium
    """
    commodity_tickers = {
        "gold": "GC=F",
        "silver": "SI=F",
        "oil": "CL=F",
        "crude": "CL=F",
        "wti": "CL=F",
        "brent": "BZ=F",
        "natural_gas": "NG=F",
        "natgas": "NG=F",
        "copper": "HG=F",
        "platinum": "PL=F",
        "palladium": "PA=F",
        "corn": "ZC=F",
        "wheat": "ZW=F",
        "soybeans": "ZS=F",
    }
    
    commodity_lower = commodity.lower().replace(" ", "_")
    ticker = commodity_tickers.get(commodity_lower)
    
    if not ticker:
        return {"status": "error", "error": f"Unknown commodity: {commodity}. Supported: {list(commodity_tickers.keys())}"}
    
    try:
        fut = yf.Ticker(ticker)
        info = fut.info
        hist = fut.history(period="1y")
        
        # Calculate returns
        if not hist.empty:
            current = hist["Close"].iloc[-1]
            ytd_start = datetime(datetime.now().year, 1, 1)
            ytd_data = hist[hist.index >= ytd_start.strftime("%Y-%m-%d")]
            ytd_return = (current / ytd_data["Close"].iloc[0] - 1) * 100 if len(ytd_data) > 0 else None
            
            # 1-month return
            one_month_ago = datetime.now() - timedelta(days=30)
            month_data = hist[hist.index >= one_month_ago.strftime("%Y-%m-%d")]
            month_return = (current / month_data["Close"].iloc[0] - 1) * 100 if len(month_data) > 0 else None
        else:
            ytd_return = None
            month_return = None
        
        result = {
            "commodity": commodity,
            "ticker": ticker,
            "price": info.get("regularMarketPrice"),
            "previous_close": info.get("previousClose"),
            "day_change_pct": info.get("regularMarketChangePercent"),
            "52w_high": info.get("fiftyTwoWeekHigh"),
            "52w_low": info.get("fiftyTwoWeekLow"),
            "ytd_return_pct": ytd_return,
            "1m_return_pct": month_return,
            "currency": info.get("currency", "USD"),
        }
        
        return {"status": "success", "data": result}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_macro_data() -> Dict[str, Any]:
    """
    Get current macro indicators: rates, DXY, VIX, yield curve.
    """
    try:
        macro_tickers = {
            "dxy": "DX-Y.NYB",  # US Dollar Index
            "vix": "^VIX",     # Volatility Index
            "tnx": "^TNX",     # 10-Year Treasury Yield
            "tyx": "^TYX",     # 30-Year Treasury Yield
            "irx": "^IRX",     # 13-Week Treasury Bill
            "fvx": "^FVX",     # 5-Year Treasury Yield
        }
        
        result = {}
        
        for name, ticker in macro_tickers.items():
            try:
                t = yf.Ticker(ticker)
                info = t.info
                result[name] = {
                    "value": info.get("regularMarketPrice"),
                    "change": info.get("regularMarketChange"),
                    "change_pct": info.get("regularMarketChangePercent"),
                }
            except:
                result[name] = {"value": None, "error": "fetch failed"}
        
        # Calculate yield curve (10y - 2y approximation using 10y - 3m)
        ten_year = result.get("tnx", {}).get("value")
        three_month = result.get("irx", {}).get("value")
        if ten_year and three_month:
            result["yield_curve_10y_3m"] = {
                "spread": ten_year - three_month,
                "inverted": ten_year < three_month,
            }
        
        return {"status": "success", "data": result}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_gold_silver_ratio() -> Dict[str, Any]:
    """
    Get the current gold/silver ratio and historical context.
    """
    try:
        gold = yf.Ticker("GC=F")
        silver = yf.Ticker("SI=F")
        
        gold_price = gold.info.get("regularMarketPrice")
        silver_price = silver.info.get("regularMarketPrice")
        
        if gold_price and silver_price:
            ratio = gold_price / silver_price
            
            # Get 1-year history for context
            gold_hist = gold.history(period="1y")
            silver_hist = silver.history(period="1y")
            
            # Calculate historical ratio range
            if not gold_hist.empty and not silver_hist.empty:
                # Align dates
                common_dates = gold_hist.index.intersection(silver_hist.index)
                gold_aligned = gold_hist.loc[common_dates]["Close"]
                silver_aligned = silver_hist.loc[common_dates]["Close"]
                ratio_history = gold_aligned / silver_aligned
                
                ratio_high = ratio_history.max()
                ratio_low = ratio_history.min()
                ratio_avg = ratio_history.mean()
            else:
                ratio_high = ratio_low = ratio_avg = None
            
            result = {
                "current_ratio": ratio,
                "gold_price": gold_price,
                "silver_price": silver_price,
                "1y_high": ratio_high,
                "1y_low": ratio_low,
                "1y_avg": ratio_avg,
                "historical_avg_note": "Long-term average is ~60, extremes range from 30 to 120",
                "interpretation": "high ratio (>80) = silver cheap vs gold, low ratio (<50) = silver expensive vs gold",
            }
            
            return {"status": "success", "data": result}
        else:
            return {"status": "error", "error": "Could not fetch gold/silver prices"}
            
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_etf_holdings(ticker: str) -> Dict[str, Any]:
    """
    Get ETF holdings (for equity ETFs).
    Note: yfinance has limited holdings data for many ETFs.
    """
    try:
        etf = yf.Ticker(ticker)
        
        # Try to get top holdings
        try:
            holdings = etf.major_holders
            holdings_data = holdings.to_dict() if hasattr(holdings, 'to_dict') else {}
        except:
            holdings_data = {}
        
        # Try to get sector weights
        try:
            if hasattr(etf, 'info') and 'sectorWeightings' in etf.info:
                sector_weights = etf.info['sectorWeightings']
            else:
                sector_weights = {}
        except:
            sector_weights = {}
        
        result = {
            "ticker": ticker,
            "holdings": holdings_data,
            "sector_weights": sector_weights,
            "note": "For detailed holdings, check ETF issuer website",
        }
        
        return {"status": "success", "data": result}
        
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Tool definitions for the agent
ETF_TOOLS = [
    {
        "name": "get_etf_info",
        "description": "Get comprehensive ETF information including expense ratio, AUM, NAV, premium/discount, and performance. Use for any ETF analysis.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "ETF ticker symbol (e.g., 'SLV', 'GLD', 'SPY')"
                }
            },
            "required": ["ticker"]
        }
    },
    {
        "name": "get_commodity_price",
        "description": "Get current price and historical data for a commodity. Supports: gold, silver, oil, natural_gas, copper, platinum, palladium, corn, wheat, soybeans.",
        "input_schema": {
            "type": "object",
            "properties": {
                "commodity": {
                    "type": "string",
                    "description": "Commodity name (e.g., 'gold', 'silver', 'oil')"
                }
            },
            "required": ["commodity"]
        }
    },
    {
        "name": "get_macro_data",
        "description": "Get current macro indicators: DXY (dollar index), VIX, Treasury yields, yield curve status. Use for macro analysis.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_gold_silver_ratio",
        "description": "Get the current gold/silver ratio and 1-year historical context. Useful for relative value analysis of precious metals.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_etf_holdings",
        "description": "Get ETF holdings and sector weights (for equity ETFs). Limited data availability for commodity ETFs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "ETF ticker symbol"
                }
            },
            "required": ["ticker"]
        }
    },
]


def execute_etf_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Execute an ETF tool and return JSON result."""
    
    tool_functions = {
        "get_etf_info": get_etf_info,
        "get_commodity_price": get_commodity_price,
        "get_macro_data": get_macro_data,
        "get_gold_silver_ratio": get_gold_silver_ratio,
        "get_etf_holdings": get_etf_holdings,
    }
    
    if tool_name not in tool_functions:
        return json.dumps({"status": "error", "error": f"Unknown tool: {tool_name}"})
    
    try:
        result = tool_functions[tool_name](**tool_input)
        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)})


if __name__ == "__main__":
    # Test the tools
    print("=== Testing ETF Tools ===\n")
    
    print("1. get_etf_info('SLV'):")
    print(execute_etf_tool("get_etf_info", {"ticker": "SLV"}))
    
    print("\n2. get_commodity_price('silver'):")
    print(execute_etf_tool("get_commodity_price", {"commodity": "silver"}))
    
    print("\n3. get_macro_data():")
    print(execute_etf_tool("get_macro_data", {}))
    
    print("\n4. get_gold_silver_ratio():")
    print(execute_etf_tool("get_gold_silver_ratio", {}))
