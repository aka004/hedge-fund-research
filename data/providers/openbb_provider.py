"""OpenBB Platform data provider for insider trading, congressional trades, news, and macro data.

Replaces the previously unused Finnhub, Reddit, Quiver, and SEC EDGAR providers
with a unified interface backed by OpenBB's free data sources.

Free data (no API key):
    - SEC insider trading (Form 4 filings via SEC EDGAR)

Optional (free API key registration):
    - FRED macro series (register at fred.stlouisfed.org)
    - FMP: congressional trades, news, fundamentals
      (register at financialmodelingprep.com, 250 free calls/day)
"""

import logging
import os
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd

from data.providers.base import DataProvider, ProviderConfig

logger = logging.getLogger(__name__)


@dataclass
class OpenBBConfig(ProviderConfig):
    """Configuration for OpenBB provider."""

    rate_limit_requests: int = 60
    rate_limit_period_seconds: int = 60
    default_price_provider: str = "yfinance"


class OpenBBProvider(DataProvider):
    """Data provider using OpenBB Platform for SEC, government, macro, and news data.

    Lazy-initializes the OpenBB SDK on first use to avoid slow import at module load.
    """

    def __init__(self, config: OpenBBConfig | None = None) -> None:
        self._config = config or OpenBBConfig()
        super().__init__(self._config)
        self._obb: Any = None

    def _ensure_initialized(self) -> Any:
        """Lazy-load OpenBB SDK on first use."""
        if self._obb is None:
            try:
                from openbb import obb

                # Set optional API keys from environment
                fred_key = os.getenv("FRED_API_KEY")
                if fred_key:
                    obb.user.credentials.fred_api_key = fred_key

                fmp_key = os.getenv("FMP_API_KEY")
                if fmp_key:
                    obb.user.credentials.fmp_api_key = fmp_key

                self._obb = obb
                logger.info("OpenBB Platform initialized")
            except ImportError:
                raise ImportError(
                    "openbb not installed. Install with: pip install openbb"
                )
        return self._obb

    @property
    def provider_name(self) -> str:
        return "openbb"

    # -------------------------------------------------------------------------
    # DataProvider ABC implementation
    # -------------------------------------------------------------------------

    def get_historical_prices(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data via OpenBB.

        Uses yfinance backend by default (free, no key).
        """
        obb = self._ensure_initialized()
        try:
            result = obb.equity.price.historical(
                symbol=symbol,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                provider=self._config.default_price_provider,
            )
            df = result.to_dataframe()
            if df.empty:
                return df

            # Normalize columns to match project convention
            column_map = {
                "adj_close": "adj_close",
                "close": "close",
                "open": "open",
                "high": "high",
                "low": "low",
                "volume": "volume",
            }
            df = df.rename(
                columns={k: v for k, v in column_map.items() if k in df.columns}
            )

            if df.index.name == "date" or "date" not in df.columns:
                df = df.reset_index()
            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"]).dt.date

            return df
        except Exception as e:
            logger.error(f"Error fetching prices for {symbol}: {e}")
            return pd.DataFrame()

    def get_fundamentals(self, symbol: str) -> dict:
        """Fetch fundamental data via OpenBB.

        Uses yfinance backend by default (free, no key).
        """
        obb = self._ensure_initialized()
        try:
            result = obb.equity.profile(symbol=symbol, provider="yfinance")
            if result.results:
                data = (
                    result.results[0].model_dump()
                    if hasattr(result.results[0], "model_dump")
                    else {}
                )
                return {"symbol": symbol, **data}
            return {"symbol": symbol}
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {symbol}: {e}")
            return {"symbol": symbol, "error": str(e)}

    # -------------------------------------------------------------------------
    # SEC insider trading (free, no API key)
    # -------------------------------------------------------------------------

    def get_insider_trading(
        self,
        symbol: str,
        limit: int = 100,
    ) -> pd.DataFrame:
        """Fetch SEC Form 4 insider trading filings.

        Free via SEC EDGAR — no API key required.

        Args:
            symbol: Ticker symbol (e.g., 'AAPL')
            limit: Maximum number of filings to return

        Returns:
            DataFrame with columns: filing_date, transaction_date, owner_name,
            owner_title, transaction_type, securities_transacted, transaction_price
        """
        obb = self._ensure_initialized()
        try:
            result = obb.equity.ownership.insider_trading(
                symbol=symbol,
                limit=limit,
                provider="sec",
                use_cache=True,
            )
            df = result.to_dataframe()
            if df.empty:
                logger.warning(f"No insider trading data for {symbol}")
            else:
                logger.info(f"Fetched {len(df)} insider trades for {symbol}")
            return df
        except Exception as e:
            logger.error(f"Error fetching insider trading for {symbol}: {e}")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # Congressional / government trades (requires FMP free key)
    # -------------------------------------------------------------------------

    def get_congressional_trades(
        self,
        symbol: str | None = None,
        chamber: str = "all",
        limit: int = 200,
    ) -> pd.DataFrame:
        """Fetch congressional stock trades (STOCK Act disclosures).

        Requires free FMP API key (set FMP_API_KEY env var).
        Register at: https://site.financialmodelingprep.com/developer/docs/pricing
        (250 free calls/day)

        Note: For free congressional trades without an API key,
        use HouseClerkProvider instead.

        Args:
            symbol: Optional ticker to filter by
            chamber: 'house', 'senate', or 'all'
            limit: Maximum number of trades to return

        Returns:
            DataFrame with columns: representative, transaction_date,
            transaction_type, amount, symbol, chamber
        """
        obb = self._ensure_initialized()

        if not os.getenv("FMP_API_KEY"):
            logger.warning(
                "FMP_API_KEY not set. Congressional trades via OpenBB require it. "
                "Use HouseClerkProvider for free congressional trades, or register "
                "for free at https://site.financialmodelingprep.com"
            )
            return pd.DataFrame()

        try:
            kwargs: dict[str, Any] = {
                "limit": limit,
                "provider": "fmp",
            }
            if symbol:
                kwargs["symbol"] = symbol
            if chamber != "all":
                kwargs["chamber"] = chamber

            result = obb.equity.ownership.government_trades(**kwargs)
            df = result.to_dataframe()
            if df.empty:
                logger.warning("No congressional trades returned")
            else:
                logger.info(f"Fetched {len(df)} congressional trades")
            return df
        except Exception as e:
            logger.error(f"Error fetching congressional trades: {e}")
            return pd.DataFrame()

    # -------------------------------------------------------------------------
    # News (requires FMP free key)
    # -------------------------------------------------------------------------

    def get_news(
        self,
        symbol: str,
        limit: int = 20,
    ) -> list[dict]:
        """Fetch recent news for a symbol.

        Requires free FMP API key (set FMP_API_KEY env var).
        Register at: https://site.financialmodelingprep.com/developer/docs/pricing

        Args:
            symbol: Ticker symbol
            limit: Maximum number of articles

        Returns:
            List of dicts with: title, date, url, source
        """
        obb = self._ensure_initialized()

        if not os.getenv("FMP_API_KEY"):
            logger.warning(
                "FMP_API_KEY not set. News via OpenBB requires it. "
                "Register for free at https://site.financialmodelingprep.com"
            )
            return []

        try:
            result = obb.news.company(
                symbol=symbol,
                limit=limit,
                provider="fmp",
            )
            articles = []
            for item in result.results[:limit]:
                data = item.model_dump() if hasattr(item, "model_dump") else {}
                articles.append(
                    {
                        "title": data.get("title", ""),
                        "date": str(data.get("date", "")),
                        "url": data.get("url", ""),
                        "source": data.get("source", ""),
                        "text": data.get("text", ""),
                    }
                )
            logger.info(f"Fetched {len(articles)} news articles for {symbol}")
            return articles
        except Exception as e:
            logger.error(f"Error fetching news for {symbol}: {e}")
            return []

    # -------------------------------------------------------------------------
    # FRED macro data (free with API key)
    # -------------------------------------------------------------------------

    def get_macro_series(
        self,
        series_id: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Fetch FRED economic time series.

        Requires free FRED API key (set FRED_API_KEY env var).
        Register at: https://fred.stlouisfed.org/docs/api/api_key.html

        Common series IDs:
            - DFF: Federal Funds Rate
            - CPIAUCSL: Consumer Price Index
            - GDP: Gross Domestic Product
            - UNRATE: Unemployment Rate
            - T10Y2Y: 10-Year minus 2-Year Treasury spread

        Args:
            series_id: FRED series identifier
            start_date: Optional start date
            end_date: Optional end date

        Returns:
            DataFrame with date and value columns
        """
        obb = self._ensure_initialized()

        if not os.getenv("FRED_API_KEY"):
            logger.warning(
                "FRED_API_KEY not set. Register for free at "
                "https://fred.stlouisfed.org/docs/api/api_key.html"
            )
            return pd.DataFrame()

        try:
            kwargs: dict[str, Any] = {
                "symbol": series_id,
                "provider": "fred",
            }
            if start_date:
                kwargs["start_date"] = start_date.isoformat()
            if end_date:
                kwargs["end_date"] = end_date.isoformat()

            result = obb.economy.fred_series(**kwargs)
            df = result.to_dataframe()
            logger.info(f"Fetched {len(df)} data points for FRED series {series_id}")
            return df
        except Exception as e:
            logger.error(f"Error fetching FRED series {series_id}: {e}")
            return pd.DataFrame()
