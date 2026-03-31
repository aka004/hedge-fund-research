"""Event type to instrument mapping and direction rules for Surprise Alpha strategy.

Provides lookup structures for which instruments are affected by macro events,
and how event outcomes map to bullish/bearish/neutral directions.
"""

from __future__ import annotations

# Macro event type → affected instruments (list of tickers)
MACRO_EVENT_INSTRUMENTS: dict[str, list[str]] = {
    "fed_rate_hike": ["TLT", "GLD", "SPY"],
    "fed_rate_cut": ["TLT", "GLD", "SPY"],
    "cpi_surprise": ["SPY", "XLF", "TLT"],
    "ppi_surprise": ["SPY", "XLE"],
    "nfp_surprise": ["SPY", "TLT"],  # Non-farm payrolls
    "gdp_surprise": ["SPY", "EFA"],
}

# Event subtype → direction (+1 = bullish, -1 = bearish, 0 = neutral)
DIRECTION_RULES: dict[str, int] = {
    # Earnings
    "earnings_beat": +1,
    "earnings_miss": -1,
    "earnings_in_line": 0,
    # Fed
    "rate_hike": -1,  # Higher rates → bonds down, stocks down short-term
    "rate_cut": +1,  # Rate cut → stocks up
    "rate_hold": 0,
    # Inflation
    "cpi_above_expected": -1,  # Hot inflation → hawkish → bearish
    "cpi_below_expected": +1,  # Cool inflation → dovish → bullish
    "ppi_above_expected": -1,
    "ppi_below_expected": +1,
    # Labor
    "nfp_above_expected": -1,  # Strong jobs → hawkish → bearish bonds
    "nfp_below_expected": +1,
    # GDP
    "gdp_above_expected": +1,
    "gdp_below_expected": -1,
}


def get_direction(event_type: str, outcome_subtype: str) -> int:
    """Map an event subtype to a direction.

    Args:
        event_type: High-level event category (e.g. "earnings", "fed_rate").
        outcome_subtype: Specific outcome key (e.g. "earnings_beat").

    Returns:
        +1 for bullish, -1 for bearish, 0 if unknown or neutral.
    """
    return DIRECTION_RULES.get(outcome_subtype, 0)


def get_instruments(event_type: str, symbol: str | None = None) -> list[str]:
    """Get affected instruments for an event type.

    For earnings events, returns [symbol] if a symbol is provided.
    For macro events, returns the pre-configured instrument list.

    Args:
        event_type: Event category (e.g. "earnings", "fed_rate_hike").
        symbol: Ticker symbol, used only for earnings events.

    Returns:
        List of affected ticker symbols.
    """
    if event_type == "earnings":
        return [symbol] if symbol else []
    return MACRO_EVENT_INSTRUMENTS.get(event_type, [])
