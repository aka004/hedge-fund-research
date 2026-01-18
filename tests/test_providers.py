"""Tests for data providers."""

from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data.providers.base import ProviderConfig
from data.providers.stocktwits import StockTwitsConfig, StockTwitsProvider
from data.providers.yahoo import YahooFinanceProvider


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_default_config(self):
        config = ProviderConfig()
        assert config.rate_limit_requests == 100
        assert config.rate_limit_period_seconds == 60
        assert config.max_retries == 3

    def test_custom_config(self):
        config = ProviderConfig(rate_limit_requests=50, max_retries=5)
        assert config.rate_limit_requests == 50
        assert config.max_retries == 5


class TestYahooFinanceProvider:
    """Tests for YahooFinanceProvider."""

    def test_provider_name(self):
        provider = YahooFinanceProvider()
        assert provider.provider_name == "yahoo_finance"

    @patch("data.providers.yahoo.yf.Ticker")
    def test_get_historical_prices(self, mock_ticker):
        # Mock the yfinance response
        mock_data = pd.DataFrame({
            "Date": pd.date_range("2024-01-01", periods=5),
            "Open": [150.0, 151.0, 152.0, 153.0, 154.0],
            "High": [155.0, 156.0, 157.0, 158.0, 159.0],
            "Low": [149.0, 150.0, 151.0, 152.0, 153.0],
            "Close": [154.0, 155.0, 156.0, 157.0, 158.0],
            "Volume": [1000000, 1100000, 1200000, 1300000, 1400000],
            "Adj Close": [154.0, 155.0, 156.0, 157.0, 158.0],
        }).set_index("Date")

        mock_ticker_instance = MagicMock()
        mock_ticker_instance.history.return_value = mock_data
        mock_ticker.return_value = mock_ticker_instance

        provider = YahooFinanceProvider()
        result = provider.get_historical_prices(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 1, 5),
        )

        assert isinstance(result, pd.DataFrame)
        assert "date" in result.columns
        assert "close" in result.columns
        assert len(result) == 5

    @patch("data.providers.yahoo.yf.Ticker")
    def test_get_fundamentals(self, mock_ticker):
        mock_info = {
            "trailingPE": 25.0,
            "forwardPE": 22.0,
            "totalRevenue": 100000000,
            "netIncomeToCommon": 10000000,
            "marketCap": 500000000,
        }

        mock_ticker_instance = MagicMock()
        mock_ticker_instance.info = mock_info
        mock_ticker.return_value = mock_ticker_instance

        provider = YahooFinanceProvider()
        result = provider.get_fundamentals("AAPL")

        assert result["pe_ratio"] == 25.0
        assert result["forward_pe"] == 22.0
        assert result["revenue"] == 100000000


class TestStockTwitsProvider:
    """Tests for StockTwitsProvider."""

    def test_provider_name(self):
        provider = StockTwitsProvider()
        assert provider.provider_name == "stocktwits"

    def test_custom_config(self):
        config = StockTwitsConfig(rate_limit_requests=100)
        provider = StockTwitsProvider(config)
        assert provider.config.rate_limit_requests == 100

    def test_get_historical_prices_raises(self):
        provider = StockTwitsProvider()
        with pytest.raises(NotImplementedError):
            provider.get_historical_prices("AAPL", date(2024, 1, 1), date(2024, 1, 5))

    def test_get_fundamentals_raises(self):
        provider = StockTwitsProvider()
        with pytest.raises(NotImplementedError):
            provider.get_fundamentals("AAPL")

    @patch("data.providers.stocktwits.requests.Session")
    def test_get_sentiment(self, mock_session):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "symbol": {"watchlist_count": 1000},
            "messages": [
                {"entities": {"sentiment": {"basic": "Bullish"}}},
                {"entities": {"sentiment": {"basic": "Bullish"}}},
                {"entities": {"sentiment": {"basic": "Bearish"}}},
            ],
        }
        mock_response.raise_for_status = MagicMock()

        mock_session_instance = MagicMock()
        mock_session_instance.get.return_value = mock_response
        mock_session.return_value = mock_session_instance

        provider = StockTwitsProvider()
        provider._session = mock_session_instance

        result = provider.get_sentiment("AAPL")

        assert result["symbol"] == "AAPL"
        assert result["bullish_count"] == 2
        assert result["bearish_count"] == 1
        assert result["sentiment_score"] == pytest.approx(1 / 3, rel=0.01)
