"""Tests for data storage."""

import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from data.storage.duckdb_store import DuckDBStore
from data.storage.parquet import ParquetStorage
from data.storage.universe import SP500_SYMBOLS, UniverseManager


class TestParquetStorage:
    """Tests for ParquetStorage."""

    @pytest.fixture
    def storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield ParquetStorage(Path(tmpdir))

    def test_save_and_load_prices(self, storage):
        df = pd.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 1, 2)],
            "open": [150.0, 151.0],
            "high": [155.0, 156.0],
            "low": [149.0, 150.0],
            "close": [154.0, 155.0],
            "volume": [1000000, 1100000],
            "adj_close": [154.0, 155.0],
        })

        storage.save_prices("AAPL", df)
        loaded = storage.load_prices("AAPL")

        assert loaded is not None
        assert len(loaded) == 2
        assert loaded["close"].iloc[0] == 154.0

    def test_load_nonexistent_prices(self, storage):
        result = storage.load_prices("NONEXISTENT")
        assert result is None

    def test_save_and_load_fundamentals(self, storage):
        data = {
            "symbol": "AAPL",
            "pe_ratio": 25.0,
            "revenue": 100000000,
        }

        storage.save_fundamentals("AAPL", data)
        loaded = storage.load_fundamentals("AAPL")

        assert loaded is not None
        assert loaded["pe_ratio"] == 25.0

    def test_list_symbols(self, storage):
        df = pd.DataFrame({
            "date": [date(2024, 1, 1)],
            "open": [150.0],
            "high": [155.0],
            "low": [149.0],
            "close": [154.0],
            "volume": [1000000],
            "adj_close": [154.0],
        })

        storage.save_prices("AAPL", df)
        storage.save_prices("GOOGL", df)

        symbols = storage.list_symbols("prices")
        assert "AAPL" in symbols
        assert "GOOGL" in symbols

    def test_delete_symbol(self, storage):
        df = pd.DataFrame({
            "date": [date(2024, 1, 1)],
            "open": [150.0],
            "high": [155.0],
            "low": [149.0],
            "close": [154.0],
            "volume": [1000000],
            "adj_close": [154.0],
        })

        storage.save_prices("AAPL", df)
        storage.delete_symbol("AAPL", "prices")

        assert storage.load_prices("AAPL") is None


class TestDuckDBStore:
    """Tests for DuckDBStore."""

    @pytest.fixture
    def store(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            parquet_path = Path(tmpdir) / "parquet"
            parquet_path.mkdir()

            # Create test data
            storage = ParquetStorage(parquet_path)
            prices = pd.DataFrame({
                "date": pd.date_range("2024-01-01", periods=300).date.tolist(),
                "open": [150.0 + i * 0.1 for i in range(300)],
                "high": [155.0 + i * 0.1 for i in range(300)],
                "low": [149.0 + i * 0.1 for i in range(300)],
                "close": [154.0 + i * 0.1 for i in range(300)],
                "volume": [1000000 + i * 1000 for i in range(300)],
                "adj_close": [154.0 + i * 0.1 for i in range(300)],
            })
            storage.save_prices("AAPL", prices)

            yield DuckDBStore(parquet_path)

    def test_get_price_returns(self, store):
        returns = store.get_price_returns(
            "AAPL",
            date(2024, 1, 1),
            date(2024, 3, 31),
        )

        assert isinstance(returns, pd.DataFrame)
        assert "return" in returns.columns

    def test_get_moving_average(self, store):
        ma = store.get_moving_average("AAPL", date(2024, 10, 1), window_days=50)
        assert ma is not None
        assert isinstance(ma, float)

    def test_get_moving_average_nonexistent(self, store):
        ma = store.get_moving_average("NONEXISTENT", date(2024, 10, 1))
        assert ma is None


class TestUniverseManager:
    """Tests for UniverseManager."""

    @pytest.fixture
    def manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield UniverseManager(Path(tmpdir))

    def test_get_sp500_symbols(self, manager):
        symbols = manager.get_sp500_symbols()
        assert len(symbols) > 0
        assert "AAPL" in symbols
        assert "MSFT" in symbols

    def test_save_and_load_custom_universe(self, manager):
        symbols = ["AAPL", "GOOGL", "MSFT"]
        manager.save_custom_universe("tech_3", symbols)

        loaded = manager.load_universe("tech_3")
        assert loaded == symbols

    def test_load_sp500_universe(self, manager):
        symbols = manager.load_universe("sp500")
        assert symbols == SP500_SYMBOLS

    def test_load_nonexistent_universe(self, manager):
        with pytest.raises(ValueError, match="not found"):
            manager.load_universe("nonexistent")

    def test_list_universes(self, manager):
        manager.save_custom_universe("test", ["AAPL"])
        universes = manager.list_universes()

        assert "sp500" in universes
        assert "test" in universes

    def test_filter_universe(self, manager):
        symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
        filtered = manager.filter_universe(symbols, exclude_symbols=["MSFT", "AMZN"])

        assert filtered == ["AAPL", "GOOGL"]
