#!/usr/bin/env python3
"""
Asset Type Classifier
=====================

Determines the asset type for a given ticker to route to appropriate
research framework (equity, ETF-commodity, ETF-index, etc.)
"""

import yfinance as yf
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any


class AssetType(Enum):
    EQUITY = "equity"
    ETF_COMMODITY = "etf_commodity"
    ETF_COMMODITY_FUTURES = "etf_commodity_futures"
    ETF_EQUITY_INDEX = "etf_equity_index"
    ETF_EQUITY_SECTOR = "etf_equity_sector"
    ETF_EQUITY_THEMATIC = "etf_equity_thematic"
    ETF_FIXED_INCOME = "etf_fixed_income"
    ETF_LEVERAGED = "etf_leveraged"
    ETF_CURRENCY = "etf_currency"
    CRYPTO = "crypto"
    UNKNOWN = "unknown"


# Known ETF classifications by ticker
KNOWN_CLASSIFICATIONS = {
    # Commodity - Physical
    "SLV": AssetType.ETF_COMMODITY,
    "GLD": AssetType.ETF_COMMODITY,
    "IAU": AssetType.ETF_COMMODITY,
    "PSLV": AssetType.ETF_COMMODITY,
    "PHYS": AssetType.ETF_COMMODITY,
    "SGOL": AssetType.ETF_COMMODITY,
    "SIVR": AssetType.ETF_COMMODITY,
    "PPLT": AssetType.ETF_COMMODITY,
    "PALL": AssetType.ETF_COMMODITY,
    
    # Commodity - Futures Based
    "USO": AssetType.ETF_COMMODITY_FUTURES,
    "UNG": AssetType.ETF_COMMODITY_FUTURES,
    "DBO": AssetType.ETF_COMMODITY_FUTURES,
    "DBA": AssetType.ETF_COMMODITY_FUTURES,
    "DBC": AssetType.ETF_COMMODITY_FUTURES,
    "PDBC": AssetType.ETF_COMMODITY_FUTURES,
    "GSG": AssetType.ETF_COMMODITY_FUTURES,
    "COMT": AssetType.ETF_COMMODITY_FUTURES,
    
    # Equity Index - Broad Market
    "SPY": AssetType.ETF_EQUITY_INDEX,
    "IVV": AssetType.ETF_EQUITY_INDEX,
    "VOO": AssetType.ETF_EQUITY_INDEX,
    "QQQ": AssetType.ETF_EQUITY_INDEX,
    "VTI": AssetType.ETF_EQUITY_INDEX,
    "IWM": AssetType.ETF_EQUITY_INDEX,
    "DIA": AssetType.ETF_EQUITY_INDEX,
    "VEA": AssetType.ETF_EQUITY_INDEX,
    "EFA": AssetType.ETF_EQUITY_INDEX,
    "VWO": AssetType.ETF_EQUITY_INDEX,
    "EEM": AssetType.ETF_EQUITY_INDEX,
    "IEMG": AssetType.ETF_EQUITY_INDEX,
    
    # Equity Sector
    "XLF": AssetType.ETF_EQUITY_SECTOR,
    "XLE": AssetType.ETF_EQUITY_SECTOR,
    "XLK": AssetType.ETF_EQUITY_SECTOR,
    "XLV": AssetType.ETF_EQUITY_SECTOR,
    "XLI": AssetType.ETF_EQUITY_SECTOR,
    "XLP": AssetType.ETF_EQUITY_SECTOR,
    "XLY": AssetType.ETF_EQUITY_SECTOR,
    "XLU": AssetType.ETF_EQUITY_SECTOR,
    "XLB": AssetType.ETF_EQUITY_SECTOR,
    "XLRE": AssetType.ETF_EQUITY_SECTOR,
    "XLC": AssetType.ETF_EQUITY_SECTOR,
    "VNQ": AssetType.ETF_EQUITY_SECTOR,
    "KRE": AssetType.ETF_EQUITY_SECTOR,
    "KBE": AssetType.ETF_EQUITY_SECTOR,
    "SMH": AssetType.ETF_EQUITY_SECTOR,
    "XBI": AssetType.ETF_EQUITY_SECTOR,
    "XOP": AssetType.ETF_EQUITY_SECTOR,
    "XHB": AssetType.ETF_EQUITY_SECTOR,
    
    # Thematic
    "ARKK": AssetType.ETF_EQUITY_THEMATIC,
    "ARKW": AssetType.ETF_EQUITY_THEMATIC,
    "ARKG": AssetType.ETF_EQUITY_THEMATIC,
    "ARKF": AssetType.ETF_EQUITY_THEMATIC,
    "ICLN": AssetType.ETF_EQUITY_THEMATIC,
    "TAN": AssetType.ETF_EQUITY_THEMATIC,
    "LIT": AssetType.ETF_EQUITY_THEMATIC,
    "BOTZ": AssetType.ETF_EQUITY_THEMATIC,
    "HACK": AssetType.ETF_EQUITY_THEMATIC,
    "SOXX": AssetType.ETF_EQUITY_THEMATIC,
    
    # Fixed Income
    "TLT": AssetType.ETF_FIXED_INCOME,
    "IEF": AssetType.ETF_FIXED_INCOME,
    "SHY": AssetType.ETF_FIXED_INCOME,
    "BND": AssetType.ETF_FIXED_INCOME,
    "AGG": AssetType.ETF_FIXED_INCOME,
    "LQD": AssetType.ETF_FIXED_INCOME,
    "HYG": AssetType.ETF_FIXED_INCOME,
    "JNK": AssetType.ETF_FIXED_INCOME,
    "TIP": AssetType.ETF_FIXED_INCOME,
    "VCIT": AssetType.ETF_FIXED_INCOME,
    "VCSH": AssetType.ETF_FIXED_INCOME,
    "MUB": AssetType.ETF_FIXED_INCOME,
    "EMB": AssetType.ETF_FIXED_INCOME,
    
    # Leveraged/Inverse
    "TQQQ": AssetType.ETF_LEVERAGED,
    "SQQQ": AssetType.ETF_LEVERAGED,
    "SPXU": AssetType.ETF_LEVERAGED,
    "SPXL": AssetType.ETF_LEVERAGED,
    "UPRO": AssetType.ETF_LEVERAGED,
    "SH": AssetType.ETF_LEVERAGED,
    "PSQ": AssetType.ETF_LEVERAGED,
    "QID": AssetType.ETF_LEVERAGED,
    "SOXL": AssetType.ETF_LEVERAGED,
    "SOXS": AssetType.ETF_LEVERAGED,
    "LABU": AssetType.ETF_LEVERAGED,
    "LABD": AssetType.ETF_LEVERAGED,
    "UVXY": AssetType.ETF_LEVERAGED,
    "SVXY": AssetType.ETF_LEVERAGED,
    "NUGT": AssetType.ETF_LEVERAGED,
    "DUST": AssetType.ETF_LEVERAGED,
    "JNUG": AssetType.ETF_LEVERAGED,
    "JDST": AssetType.ETF_LEVERAGED,
    
    # Currency
    "UUP": AssetType.ETF_CURRENCY,
    "FXE": AssetType.ETF_CURRENCY,
    "FXY": AssetType.ETF_CURRENCY,
    "FXB": AssetType.ETF_CURRENCY,
}

# Category keywords for classification
CATEGORY_KEYWORDS = {
    AssetType.ETF_COMMODITY: ["commodit", "gold", "silver", "metal", "precious"],
    AssetType.ETF_EQUITY_INDEX: ["large blend", "large growth", "large value", 
                                  "mid-cap", "small blend", "small growth", "small value",
                                  "total stock", "s&p 500", "nasdaq"],
    AssetType.ETF_EQUITY_SECTOR: ["sector", "financ", "technolog", "health", "energy",
                                   "industrial", "consumer", "utilities", "real estate"],
    AssetType.ETF_FIXED_INCOME: ["bond", "treasury", "corporate", "fixed income",
                                  "government", "municipal", "high yield", "investment grade"],
    AssetType.ETF_LEVERAGED: ["leveraged", "inverse", "ultra", "2x", "3x", "-1x", "-2x", "-3x"],
}


@dataclass
class AssetInfo:
    ticker: str
    asset_type: AssetType
    name: str
    category: Optional[str]
    fund_family: Optional[str]
    expense_ratio: Optional[float]
    aum: Optional[float]
    description: Optional[str]
    raw_info: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticker": self.ticker,
            "asset_type": self.asset_type.value,
            "name": self.name,
            "category": self.category,
            "fund_family": self.fund_family,
            "expense_ratio": self.expense_ratio,
            "aum": self.aum,
            "description": self.description,
        }


def classify_asset(ticker: str) -> AssetInfo:
    """
    Classify an asset by ticker symbol.
    Returns AssetInfo with type and basic metadata.
    """
    ticker = ticker.upper()
    
    # Check known classifications first
    if ticker in KNOWN_CLASSIFICATIONS:
        known_type = KNOWN_CLASSIFICATIONS[ticker]
    else:
        known_type = None
    
    # Fetch info from yfinance
    try:
        yf_ticker = yf.Ticker(ticker)
        info = yf_ticker.info
    except Exception as e:
        return AssetInfo(
            ticker=ticker,
            asset_type=known_type or AssetType.UNKNOWN,
            name=ticker,
            category=None,
            fund_family=None,
            expense_ratio=None,
            aum=None,
            description=None,
            raw_info={},
        )
    
    quote_type = info.get("quoteType", "").upper()
    category = info.get("category", "")
    name = info.get("longName") or info.get("shortName") or ticker
    fund_family = info.get("fundFamily")
    expense_ratio = info.get("netExpenseRatio")
    aum = info.get("totalAssets")
    description = info.get("longBusinessSummary")
    
    # If known type, use it
    if known_type:
        asset_type = known_type
    # Classify by quote type
    elif quote_type == "ETF":
        asset_type = _classify_etf(info, category)
    elif quote_type in ["EQUITY", "STOCK"]:
        asset_type = AssetType.EQUITY
    elif quote_type == "CRYPTOCURRENCY":
        asset_type = AssetType.CRYPTO
    else:
        asset_type = AssetType.UNKNOWN
    
    return AssetInfo(
        ticker=ticker,
        asset_type=asset_type,
        name=name,
        category=category,
        fund_family=fund_family,
        expense_ratio=expense_ratio,
        aum=aum,
        description=description,
        raw_info=info,
    )


def _classify_etf(info: Dict[str, Any], category: str) -> AssetType:
    """Classify ETF by category and name keywords."""
    category_lower = category.lower() if category else ""
    name_lower = (info.get("longName") or "").lower()
    combined = category_lower + " " + name_lower
    
    # Check for leveraged/inverse first (highest priority)
    for keyword in CATEGORY_KEYWORDS[AssetType.ETF_LEVERAGED]:
        if keyword in combined:
            return AssetType.ETF_LEVERAGED
    
    # Check for fixed income
    for keyword in CATEGORY_KEYWORDS[AssetType.ETF_FIXED_INCOME]:
        if keyword in combined:
            return AssetType.ETF_FIXED_INCOME
    
    # Check for commodity
    for keyword in CATEGORY_KEYWORDS[AssetType.ETF_COMMODITY]:
        if keyword in combined:
            # Determine if physical or futures
            if "future" in combined or "oil" in combined or "natural gas" in combined:
                return AssetType.ETF_COMMODITY_FUTURES
            return AssetType.ETF_COMMODITY
    
    # Check for sector
    for keyword in CATEGORY_KEYWORDS[AssetType.ETF_EQUITY_SECTOR]:
        if keyword in combined:
            return AssetType.ETF_EQUITY_SECTOR
    
    # Check for index
    for keyword in CATEGORY_KEYWORDS[AssetType.ETF_EQUITY_INDEX]:
        if keyword in combined:
            return AssetType.ETF_EQUITY_INDEX
    
    # Default to thematic for uncategorized equity ETFs
    return AssetType.ETF_EQUITY_THEMATIC


def get_etf_research_agents(asset_type: AssetType) -> list:
    """Return the list of agents to use for a given asset type."""
    
    if asset_type == AssetType.EQUITY:
        return [
            "01-DATA-AGENT",
            "02-QUANT-AGENT",
            "03-RISK-AGENT",
            "04-COMPETITIVE-AGENT",
            "05-QUALITATIVE-AGENT",
            "06-SYNTHESIS-AGENT",
        ]
    
    elif asset_type == AssetType.ETF_COMMODITY:
        return [
            "01-ETF-STRUCTURE-AGENT",
            "02-COMMODITY-FUNDAMENTALS-AGENT",
            "03-MACRO-AGENT",
            "04-TECHNICAL-AGENT",
            "05-ETF-SYNTHESIS-AGENT",
        ]
    
    elif asset_type == AssetType.ETF_COMMODITY_FUTURES:
        return [
            "01-ETF-STRUCTURE-AGENT",
            "02-COMMODITY-FUNDAMENTALS-AGENT",
            "03-FUTURES-CURVE-AGENT",  # contango/backwardation
            "04-MACRO-AGENT",
            "05-TECHNICAL-AGENT",
            "06-ETF-SYNTHESIS-AGENT",
        ]
    
    elif asset_type in [AssetType.ETF_EQUITY_INDEX, AssetType.ETF_EQUITY_SECTOR, 
                        AssetType.ETF_EQUITY_THEMATIC]:
        return [
            "01-ETF-STRUCTURE-AGENT",
            "02-HOLDINGS-ANALYSIS-AGENT",
            "03-MACRO-AGENT",
            "04-TECHNICAL-AGENT",
            "05-ETF-SYNTHESIS-AGENT",
        ]
    
    elif asset_type == AssetType.ETF_FIXED_INCOME:
        return [
            "01-ETF-STRUCTURE-AGENT",
            "02-FIXED-INCOME-AGENT",
            "03-MACRO-AGENT",
            "04-TECHNICAL-AGENT",
            "05-ETF-SYNTHESIS-AGENT",
        ]
    
    elif asset_type == AssetType.ETF_LEVERAGED:
        return [
            "01-ETF-STRUCTURE-AGENT",
            "02-LEVERAGE-DECAY-AGENT",
            "03-UNDERLYING-AGENT",
            "04-TECHNICAL-AGENT",
            "05-ETF-SYNTHESIS-AGENT",
        ]
    
    else:
        # Unknown - use basic structure
        return [
            "01-ETF-STRUCTURE-AGENT",
            "02-MACRO-AGENT",
            "03-TECHNICAL-AGENT",
            "04-ETF-SYNTHESIS-AGENT",
        ]


if __name__ == "__main__":
    import sys
    
    tickers = sys.argv[1:] if len(sys.argv) > 1 else ["SLV", "GLD", "SPY", "AAPL", "TLT", "TQQQ", "USO"]
    
    for ticker in tickers:
        info = classify_asset(ticker)
        print(f"\n{ticker}:")
        print(f"  Type: {info.asset_type.value}")
        print(f"  Name: {info.name}")
        print(f"  Category: {info.category}")
        if info.expense_ratio:
            print(f"  Expense Ratio: {info.expense_ratio:.2%}")
        if info.aum:
            print(f"  AUM: ${info.aum/1e9:.2f}B")
        print(f"  Agents: {get_etf_research_agents(info.asset_type)}")
