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
    from data.providers.finnhub import FinnhubProvider

    __all__.append("FinnhubProvider")
except ImportError:
    FinnhubProvider = None  # type: ignore[misc, assignment]

try:
    from data.providers.reddit import RedditProvider

    __all__.append("RedditProvider")
except ImportError:
    RedditProvider = None  # type: ignore[misc, assignment]
