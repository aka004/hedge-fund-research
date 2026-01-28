#!/usr/bin/env python3
"""
Unit test for Data Agent with tools.
Tests tool calling without running full pipeline.
"""

import os
import sys
import json
from datetime import datetime

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_tools import AGENT_TOOLS, execute_tool

def test_tools_available():
    """Test all tools are defined."""
    print("=== Testing Tool Definitions ===")
    tool_names = [t["name"] for t in AGENT_TOOLS]
    print(f"Tools available: {tool_names}")
    
    required = ["get_price_data", "get_company_info", "get_analyst_estimates", 
                "web_search", "get_sec_filings", "web_fetch"]
    
    for tool in required:
        assert tool in tool_names, f"Missing tool: {tool}"
    print("✓ All required tools defined\n")

def test_analyst_estimates(ticker="MU"):
    """Test analyst estimates tool."""
    print(f"=== Testing get_analyst_estimates({ticker}) ===")
    
    result = execute_tool("get_analyst_estimates", {"ticker": ticker})
    data = json.loads(result)
    
    print(f"Price targets:")
    print(f"  High: ${data['price_targets']['high']}")
    print(f"  Mean: ${data['price_targets']['mean']:.2f}")
    print(f"  Low: ${data['price_targets']['low']}")
    print(f"  Current: ${data['price_targets']['current_price']:.2f}")
    print(f"  Upside to mean: {data['price_targets']['upside_to_mean']}%")
    print(f"Recommendation: {data['recommendation']['rating']} ({data['recommendation']['num_analysts']} analysts)")
    
    if data['earnings_estimates']:
        print(f"EPS estimates:")
        for est in data['earnings_estimates'][:2]:
            print(f"  {est['period']}: ${est['avg_eps']:.2f} (range: ${est['low_eps']:.2f}-${est['high_eps']:.2f})")
    
    if data['revenue_estimates']:
        print(f"Revenue estimates:")
        for est in data['revenue_estimates'][:2]:
            print(f"  {est['period']}: ${est['avg_revenue']/1e9:.1f}B")
    
    assert data['price_targets']['mean'] is not None, "Missing price target"
    assert data['recommendation']['rating'] is not None, "Missing recommendation"
    print("✓ Analyst estimates working\n")
    
    return data

def test_price_data(ticker="MU"):
    """Test price data tool."""
    print(f"=== Testing get_price_data({ticker}) ===")
    
    result = execute_tool("get_price_data", {"ticker": ticker})
    data = json.loads(result)
    
    print(f"Current price: ${data['data']['current_price']:.2f}")
    print(f"Market cap: ${data['data']['market_cap']/1e9:.1f}B")
    print(f"P/E: {data['data']['pe_ratio']:.1f}")
    
    assert data['data']['current_price'] is not None, "Missing price"
    print("✓ Price data working\n")
    
    return data

def estimate_token_cost(num_tool_calls=7):
    """Estimate token cost for Data Agent."""
    print(f"=== Token Cost Estimate (max {num_tool_calls} tool calls) ===")
    
    # Rough estimates per tool call
    costs = {
        "get_price_data": 2000,  # ~2K tokens response
        "get_company_info": 1500,
        "get_analyst_estimates": 2500,
        "web_search": 3000,
        "get_sec_filings": 1500,
        "web_fetch": 5000,
    }
    
    # Typical call pattern
    typical_calls = [
        "get_price_data",
        "get_company_info", 
        "get_analyst_estimates",
        "web_search",  # news
        "web_search",  # more news
        "get_sec_filings",
        "web_search",  # industry
    ][:num_tool_calls]
    
    base_prompt = 3000  # Initial prompt
    output = 4000  # Final output
    
    tool_tokens = sum(costs.get(t, 2000) for t in typical_calls)
    # Each tool call adds context accumulation
    context_growth = sum(costs.get(t, 2000) * 0.5 * i for i, t in enumerate(typical_calls))
    
    total_input = base_prompt + tool_tokens + context_growth
    total_output = output + len(typical_calls) * 500  # Tool call outputs
    
    cost_input = total_input / 1e6 * 3  # $3/MTok
    cost_output = total_output / 1e6 * 15  # $15/MTok
    
    print(f"Estimated tokens:")
    print(f"  Input: ~{total_input/1000:.0f}K")
    print(f"  Output: ~{total_output/1000:.0f}K")
    print(f"Estimated cost: ${cost_input + cost_output:.2f}")
    print(f"  (vs previous 250K tokens / $1.35 with 13 calls)")
    print()

if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "MU"
    
    test_tools_available()
    test_price_data(ticker)
    test_analyst_estimates(ticker)
    estimate_token_cost(7)
    
    print("=== All Tests Passed ===")
