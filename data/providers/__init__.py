"""Data providers for fetching market data."""

from data.providers.base import DataProvider
from data.providers.stocktwits import StockTwitsProvider
from data.providers.yahoo import YahooFinanceProvider

__all__ = [
    "DataProvider",
    "YahooFinanceProvider",
    "StockTwitsProvider",
]

# Optional providers - only available if dependencies are installed
try:
    from data.providers.house_clerk import HouseClerkProvider

    __all__.append("HouseClerkProvider")
except ImportError:
    HouseClerkProvider = None  # type: ignore[misc, assignment]

try:
    from data.providers.openbb_provider import OpenBBProvider

    __all__.append("OpenBBProvider")
except ImportError:
    OpenBBProvider = None  # type: ignore[misc, assignment]
