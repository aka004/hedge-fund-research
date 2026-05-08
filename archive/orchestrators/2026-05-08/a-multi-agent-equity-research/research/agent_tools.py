#!/usr/bin/env python3
"""
Agent Tools - Tools that research agents can call
==================================================

Provides real data fetching capabilities to agents via Anthropic's tool_use API.

Tools:
- web_search: Search for news and information
- web_fetch: Fetch and extract content from a URL
- get_price_data: Get current stock price and fundamentals
- get_sec_filings: Get recent SEC filings list

Usage:
    from agent_tools import AGENT_TOOLS, execute_tool
    
    # Pass tools to Claude API
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        tools=AGENT_TOOLS,
        messages=[...]
    )
    
    # Execute tool calls
    for block in response.content:
        if block.type == "tool_use":
            result = execute_tool(block.name, block.input)
"""

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import requests

# Try imports
try:
    import yfinance as yf

    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False


# =============================================================================
# TOOL DEFINITIONS (for Anthropic API)
# =============================================================================

AGENT_TOOLS = [
    {
        "name": "web_search",
        "description": "Search the web for recent news, articles, and information about a company or topic. Returns titles, sources, and snippets. Use this to find real sources to cite.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'Micron Technology HBM AI demand 2026')",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 5, max: 10)",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "web_fetch",
        "description": "Fetch and extract the main content from a webpage URL. Use this to read articles, press releases, or SEC filings. Returns the text content.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to fetch (must be http or https)",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return (default: 5000)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_price_data",
        "description": "Get current stock price, fundamentals, and key metrics for a ticker. Returns verified market data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {
                    "type": "string",
                    "description": "Stock ticker symbol (e.g., 'MU', 'AAPL')",
                }
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_sec_filings",
        "description": "Get list of recent SEC filings for a company. Returns filing types, dates, and URLs.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"},
                "filing_type": {
                    "type": "string",
                    "description": "Filter by filing type (e.g., '10-K', '10-Q', '8-K'). Leave empty for all.",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of filings to return (default: 5)",
                },
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_company_info",
        "description": "Get company overview including sector, industry, description, and employee count.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["ticker"],
        },
    },
    {
        "name": "get_analyst_estimates",
        "description": "Get analyst price targets, recommendations, and earnings/revenue estimates. Use this for DCF inputs instead of making up numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {"type": "string", "description": "Stock ticker symbol"}
            },
            "required": ["ticker"],
        },
    },
]


# =============================================================================
# TOOL IMPLEMENTATIONS
# =============================================================================


def _web_search(query: str, max_results: int = 5) -> dict[str, Any]:
    """Search using Google News RSS (free, no API key)."""
    try:
        encoded_query = quote_plus(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

        response = requests.get(
            rss_url, timeout=10, headers={"User-Agent": "Mozilla/5.0 (research-agent)"}
        )

        if response.status_code != 200:
            return {
                "error": f"Search failed: HTTP {response.status_code}",
                "results": [],
            }

        results = []
        items = re.findall(r"<item>(.*?)</item>", response.text, re.DOTALL)

        for item in items[: min(max_results, 10)]:
            title_match = re.search(r"<title>(.*?)</title>", item)
            link_match = re.search(r"<link>(.*?)</link>", item)
            date_match = re.search(r"<pubDate>(.*?)</pubDate>", item)
            source_match = re.search(r"<source.*?>(.*?)</source>", item)

            if title_match:
                title = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", title_match.group(1))
                title = title.replace("&amp;", "&").replace("&quot;", '"')

                results.append(
                    {
                        "title": title,
                        "source": source_match.group(1) if source_match else "Unknown",
                        "date": date_match.group(1)[:16] if date_match else "Recent",
                        "url": link_match.group(1) if link_match else "",
                    }
                )

        return {"query": query, "result_count": len(results), "results": results}

    except Exception as e:
        return {"error": str(e), "results": []}


def _web_fetch(url: str, max_chars: int = 5000) -> dict[str, Any]:
    """Fetch and extract content from a URL."""
    try:
        response = requests.get(
            url, timeout=15, headers={"User-Agent": "Mozilla/5.0 (research-agent)"}
        )

        if response.status_code != 200:
            return {
                "error": f"Fetch failed: HTTP {response.status_code}",
                "content": "",
            }

        # Simple HTML to text extraction
        text = response.text

        # Remove script and style tags
        text = re.sub(
            r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE
        )
        text = re.sub(
            r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE
        )

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Decode entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")

        # Truncate
        if len(text) > max_chars:
            text = text[:max_chars] + "... [truncated]"

        return {"url": url, "char_count": len(text), "content": text}

    except Exception as e:
        return {"error": str(e), "content": ""}


def _get_price_data(ticker: str) -> dict[str, Any]:
    """Get current price and fundamentals from yfinance."""
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not available", "data": {}}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "fetched_at": datetime.now().isoformat(),
            "source": "yfinance",
            "data": {
                "current_price": info.get("currentPrice")
                or info.get("regularMarketPrice"),
                "previous_close": info.get("previousClose"),
                "day_high": info.get("dayHigh"),
                "day_low": info.get("dayLow"),
                "week_52_high": info.get("fiftyTwoWeekHigh"),
                "week_52_low": info.get("fiftyTwoWeekLow"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "eps_ttm": info.get("trailingEps"),
                "revenue_ttm": info.get("totalRevenue"),
                "gross_margin": info.get("grossMargins"),
                "operating_margin": info.get("operatingMargins"),
                "profit_margin": info.get("profitMargins"),
                "roe": info.get("returnOnEquity"),
                "debt_to_equity": info.get("debtToEquity"),
                "free_cash_flow": info.get("freeCashflow"),
                "dividend_yield": info.get("dividendYield"),
                "beta": info.get("beta"),
            },
        }

    except Exception as e:
        return {"error": str(e), "data": {}}


def _get_sec_filings(
    ticker: str, filing_type: str = "", max_results: int = 5
) -> dict[str, Any]:
    """Get recent SEC filings from EDGAR."""
    try:
        type_filter = f"&type={filing_type}" if filing_type else ""
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}{type_filter}&dateb=&owner=include&count={max_results}&output=atom"

        response = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (research-agent; contact@example.com)"},
        )

        if response.status_code != 200:
            return {
                "error": f"SEC lookup failed: HTTP {response.status_code}",
                "filings": [],
            }

        filings = []
        entries = re.findall(r"<entry>(.*?)</entry>", response.text, re.DOTALL)

        for entry in entries[:max_results]:
            title_match = re.search(r"<title>(.*?)</title>", entry)
            link_match = re.search(r'<link href="(.*?)"', entry)
            date_match = re.search(r"<updated>(.*?)</updated>", entry)

            if title_match and link_match:
                title = title_match.group(1)
                filing_type_extracted = (
                    title.split(" - ")[0] if " - " in title else title[:20]
                )

                filings.append(
                    {
                        "filing_type": filing_type_extracted.strip(),
                        "date": date_match.group(1)[:10] if date_match else "Unknown",
                        "description": title,
                        "url": link_match.group(1),
                    }
                )

        return {"ticker": ticker, "filing_count": len(filings), "filings": filings}

    except Exception as e:
        return {"error": str(e), "filings": []}


def _get_company_info(ticker: str) -> dict[str, Any]:
    """Get company overview from yfinance."""
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not available", "info": {}}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        return {
            "ticker": ticker,
            "info": {
                "name": info.get("longName", ticker),
                "sector": info.get("sector", ""),
                "industry": info.get("industry", ""),
                "description": info.get("longBusinessSummary", "")[:1000],
                "website": info.get("website", ""),
                "employees": info.get("fullTimeEmployees", 0),
                "headquarters": f"{info.get('city', '')}, {info.get('state', '')}, {info.get('country', '')}",
            },
        }

    except Exception as e:
        return {"error": str(e), "info": {}}


def _get_analyst_estimates(ticker: str) -> dict[str, Any]:
    """Get analyst price targets and earnings/revenue estimates from yfinance."""
    if not YFINANCE_AVAILABLE:
        return {"error": "yfinance not available", "estimates": {}}

    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        result = {
            "ticker": ticker,
            "fetched_at": datetime.now().isoformat(),
            "source": "yfinance (analyst consensus)",
            "price_targets": {
                "high": info.get("targetHighPrice"),
                "low": info.get("targetLowPrice"),
                "mean": info.get("targetMeanPrice"),
                "median": info.get("targetMedianPrice"),
                "current_price": info.get("currentPrice")
                or info.get("regularMarketPrice"),
                "upside_to_mean": None,
            },
            "recommendation": {
                "rating": info.get("recommendationKey"),
                "num_analysts": info.get("numberOfAnalystOpinions"),
            },
            "earnings_estimates": [],
            "revenue_estimates": [],
        }

        # Calculate upside
        if result["price_targets"]["mean"] and result["price_targets"]["current_price"]:
            current = result["price_targets"]["current_price"]
            target = result["price_targets"]["mean"]
            result["price_targets"]["upside_to_mean"] = round(
                (target - current) / current * 100, 1
            )

        # Get earnings estimates
        try:
            earnings_est = stock.earnings_estimate
            if earnings_est is not None and not earnings_est.empty:
                for idx, row in earnings_est.iterrows():
                    result["earnings_estimates"].append(
                        {
                            "period": str(idx),
                            "avg_eps": row.get("avg"),
                            "low_eps": row.get("low"),
                            "high_eps": row.get("high"),
                            "year_ago_eps": row.get("yearAgoEps"),
                            "num_analysts": row.get("numberOfAnalysts"),
                            "growth": row.get("growth"),
                        }
                    )
        except:
            pass

        # Get revenue estimates
        try:
            revenue_est = stock.revenue_estimate
            if revenue_est is not None and not revenue_est.empty:
                for idx, row in revenue_est.iterrows():
                    result["revenue_estimates"].append(
                        {
                            "period": str(idx),
                            "avg_revenue": row.get("avg"),
                            "low_revenue": row.get("low"),
                            "high_revenue": row.get("high"),
                            "year_ago_revenue": row.get("yearAgoRevenue"),
                            "num_analysts": row.get("numberOfAnalysts"),
                            "growth": row.get("growth"),
                        }
                    )
        except:
            pass

        return result

    except Exception as e:
        return {"error": str(e), "estimates": {}}


# =============================================================================
# TOOL EXECUTOR
# =============================================================================


def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """
    Execute a tool and return the result as a JSON string.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        JSON string with the tool result
    """
    executors = {
        "web_search": lambda inp: _web_search(
            inp.get("query", ""), inp.get("max_results", 5)
        ),
        "web_fetch": lambda inp: _web_fetch(
            inp.get("url", ""), inp.get("max_chars", 5000)
        ),
        "get_price_data": lambda inp: _get_price_data(inp.get("ticker", "")),
        "get_sec_filings": lambda inp: _get_sec_filings(
            inp.get("ticker", ""), inp.get("filing_type", ""), inp.get("max_results", 5)
        ),
        "get_company_info": lambda inp: _get_company_info(inp.get("ticker", "")),
        "get_analyst_estimates": lambda inp: _get_analyst_estimates(
            inp.get("ticker", "")
        ),
        # Alias for backward compatibility (orchestrator.py used this name)
        "get_company_overview": lambda inp: _get_company_info(inp.get("ticker", "")),
    }

    if tool_name not in executors:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})

    try:
        result = executors[tool_name](tool_input)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# =============================================================================
# CLI TEST
# =============================================================================

if __name__ == "__main__":
    import sys

    print("=== Testing Agent Tools ===\n")

    ticker = sys.argv[1] if len(sys.argv) > 1 else "MU"

    # Test web_search
    print(f"1. web_search('{ticker} earnings 2026'):")
    result = execute_tool(
        "web_search", {"query": f"{ticker} earnings 2026", "max_results": 3}
    )
    print(result[:500] + "...\n")

    # Test get_price_data
    print(f"2. get_price_data('{ticker}'):")
    result = execute_tool("get_price_data", {"ticker": ticker})
    print(result[:500] + "...\n")

    # Test get_sec_filings
    print(f"3. get_sec_filings('{ticker}'):")
    result = execute_tool("get_sec_filings", {"ticker": ticker, "max_results": 3})
    print(result[:500] + "...\n")

    # Test get_company_info
    print(f"4. get_company_info('{ticker}'):")
    result = execute_tool("get_company_info", {"ticker": ticker})
    print(result[:500] + "...\n")

    print("=== All tools working ===")
