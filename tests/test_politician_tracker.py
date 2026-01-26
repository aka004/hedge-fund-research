"""Tests for politician tracker components."""

from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from analysis.politician_tracker import PoliticianPerformance, PoliticianTracker
from data.storage.parquet import ParquetStorage
from data.storage.politician_trades import PoliticianTradeStorage


class TestPoliticianTradeStorage:
    """Tests for PoliticianTradeStorage."""

    def test_init(self, tmp_path):
        """Test storage initialization."""
        storage = PoliticianTradeStorage(tmp_path)
        assert storage.base_path == tmp_path
        assert storage.trades_dir.exists()

    def test_save_and_load_trades(self, tmp_path):
        """Test saving and loading trades."""
        storage = PoliticianTradeStorage(tmp_path)
        
        # Create sample trades
        trades_df = pd.DataFrame({
            "politician_name": ["Test Politician"],
            "cik": ["0001234567"],
            "transaction_date": [date(2024, 1, 15)],
            "filing_date": [date(2024, 1, 20)],
            "symbol": ["AAPL"],
            "transaction_type": ["Buy"],
            "shares": [100.0],
            "price": [150.0],
        })
        
        # Save
        storage.save_trades("Test Politician", trades_df)
        
        # Load
        loaded = storage.load_trades("Test Politician")
        
        assert loaded is not None
        assert len(loaded) == 1
        assert loaded.iloc[0]["symbol"] == "AAPL"

    def test_list_politicians(self, tmp_path):
        """Test listing politicians."""
        storage = PoliticianTradeStorage(tmp_path)
        
        # Save trades for two politicians
        trades1 = pd.DataFrame({
            "politician_name": ["Politician A"],
            "cik": ["0001111111"],
            "transaction_date": [date(2024, 1, 1)],
            "filing_date": [date(2024, 1, 5)],
            "symbol": ["AAPL"],
            "transaction_type": ["Buy"],
            "shares": [100.0],
            "price": [150.0],
        })
        
        trades2 = pd.DataFrame({
            "politician_name": ["Politician B"],
            "cik": ["0002222222"],
            "transaction_date": [date(2024, 1, 1)],
            "filing_date": [date(2024, 1, 5)],
            "symbol": ["MSFT"],
            "transaction_type": ["Buy"],
            "shares": [50.0],
            "price": [300.0],
        })
        
        storage.save_trades("Politician A", trades1)
        storage.save_trades("Politician B", trades2)
        
        politicians = storage.list_politicians()
        assert len(politicians) == 2
        assert "Politician A" in politicians
        assert "Politician B" in politicians


class TestPoliticianTracker:
    """Tests for PoliticianTracker."""

    def test_calculate_performance_no_trades(self, tmp_path):
        """Test performance calculation with no trades."""
        trade_storage = PoliticianTradeStorage(tmp_path)
        price_storage = ParquetStorage(tmp_path)
        
        tracker = PoliticianTracker(trade_storage, price_storage)
        performance = tracker.calculate_performance("Unknown Politician")
        
        assert performance.politician_name == "Unknown Politician"
        assert performance.total_trades == 0
        assert performance.win_rate == 0.0

    def test_calculate_performance_with_trades(self, tmp_path):
        """Test performance calculation with sample trades."""
        trade_storage = PoliticianTradeStorage(tmp_path)
        price_storage = ParquetStorage(tmp_path)
        
        # Create sample trades
        trades_df = pd.DataFrame({
            "politician_name": ["Test Politician"] * 2,
            "cik": ["0001234567"] * 2,
            "transaction_date": [date(2024, 1, 1), date(2024, 2, 1)],
            "filing_date": [date(2024, 1, 5), date(2024, 2, 5)],
            "symbol": ["AAPL", "AAPL"],
            "transaction_type": ["Buy", "Sell"],
            "shares": [100.0, 100.0],
            "price": [150.0, 160.0],  # Profitable trade
        })
        
        trade_storage.save_trades("Test Politician", trades_df)
        
        # Mock price storage to return prices
        with patch.object(price_storage, "load_prices") as mock_load:
            mock_load.return_value = None
            
            tracker = PoliticianTracker(trade_storage, price_storage)
            performance = tracker.calculate_performance("Test Politician")
            
            assert performance.total_trades == 2
            assert performance.buy_trades == 1
            assert performance.sell_trades == 1
            # Should have calculated return (160-150)/150 = 6.67%
            assert performance.avg_return > 0

    def test_get_recent_trades(self, tmp_path):
        """Test getting recent trades."""
        trade_storage = PoliticianTradeStorage(tmp_path)
        price_storage = ParquetStorage(tmp_path)
        
        # Create trades
        trades_df = pd.DataFrame({
            "politician_name": ["Test Politician"] * 3,
            "cik": ["0001234567"] * 3,
            "transaction_date": [
                date.today() - timedelta(days=10),
                date.today() - timedelta(days=5),
                date.today() - timedelta(days=60),  # Too old
            ],
            "filing_date": [
                date.today() - timedelta(days=8),
                date.today() - timedelta(days=3),
                date.today() - timedelta(days=58),
            ],
            "symbol": ["AAPL", "MSFT", "GOOGL"],
            "transaction_type": ["Buy", "Buy", "Buy"],
            "shares": [100.0, 50.0, 25.0],
            "price": [150.0, 300.0, 100.0],
        })
        
        trade_storage.save_trades("Test Politician", trades_df)
        
        tracker = PoliticianTracker(trade_storage, price_storage)
        recent = tracker.get_recent_trades("Test Politician", lookback_days=30)
        
        # Should only return trades within 30 days
        assert len(recent) == 2
        assert "AAPL" in recent["symbol"].values
        assert "MSFT" in recent["symbol"].values
        assert "GOOGL" not in recent["symbol"].values


class TestPoliticianPerformance:
    """Tests for PoliticianPerformance dataclass."""

    def test_default_values(self):
        """Test default performance values."""
        perf = PoliticianPerformance(
            politician_name="Test",
            total_trades=0,
            buy_trades=0,
            sell_trades=0,
            win_rate=0.0,
            avg_return=0.0,
            avg_holding_period_days=0.0,
        )
        
        assert perf.politician_name == "Test"
        assert perf.sharpe_ratio is None
