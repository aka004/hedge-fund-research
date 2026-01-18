"""DuckDB-based query layer for efficient data analysis."""

import logging
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

logger = logging.getLogger(__name__)


class DuckDBStore:
    """Query layer using DuckDB for efficient analytics on parquet files."""

    def __init__(self, parquet_path: Path, cache_path: Path | None = None) -> None:
        """Initialize DuckDB store.

        Args:
            parquet_path: Path to parquet storage directory
            cache_path: Optional path for DuckDB cache database
        """
        self.parquet_path = Path(parquet_path)
        self.cache_path = cache_path

        # Create in-memory or file-based connection
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = duckdb.connect(str(cache_path))
        else:
            self._conn = duckdb.connect(":memory:")

        self._setup_views()

    def _setup_views(self) -> None:
        """Set up views for parquet files."""
        prices_dir = self.parquet_path / "prices"
        if prices_dir.exists() and list(prices_dir.glob("*.parquet")):
            self._conn.execute(f"""
                CREATE OR REPLACE VIEW prices AS
                SELECT * FROM read_parquet('{prices_dir}/*.parquet', filename=true)
            """)

        fundamentals_dir = self.parquet_path / "fundamentals"
        if fundamentals_dir.exists() and list(fundamentals_dir.glob("*.parquet")):
            self._conn.execute(f"""
                CREATE OR REPLACE VIEW fundamentals AS
                SELECT * FROM read_parquet('{fundamentals_dir}/*.parquet', filename=true)
            """)

    def refresh_views(self) -> None:
        """Refresh DuckDB views after new data is added."""
        self._setup_views()

    def query(self, sql: str) -> pd.DataFrame:
        """Execute a SQL query and return results as DataFrame.

        Args:
            sql: SQL query string

        Returns:
            Query results as DataFrame
        """
        return self._conn.execute(sql).fetchdf()

    def get_price_returns(
        self,
        symbol: str,
        start_date: date,
        end_date: date,
        use_adjusted: bool = True,
    ) -> pd.DataFrame:
        """Calculate daily returns for a symbol.

        Args:
            symbol: Ticker symbol
            start_date: Start date
            end_date: End date
            use_adjusted: Use adjusted close prices

        Returns:
            DataFrame with date and return columns
        """
        price_col = "adj_close" if use_adjusted else "close"
        file_path = self.parquet_path / "prices" / f"{symbol}.parquet"

        if not file_path.exists():
            return pd.DataFrame(columns=["date", "return"])

        query = f"""
            WITH price_data AS (
                SELECT
                    date,
                    {price_col} as price,
                    LAG({price_col}) OVER (ORDER BY date) as prev_price
                FROM read_parquet('{file_path}')
                WHERE date >= '{start_date}' AND date <= '{end_date}'
                ORDER BY date
            )
            SELECT
                date,
                (price - prev_price) / prev_price as return
            FROM price_data
            WHERE prev_price IS NOT NULL
        """

        return self._conn.execute(query).fetchdf()

    def get_momentum(
        self,
        symbol: str,
        as_of_date: date,
        lookback_months: int = 12,
        skip_months: int = 1,
    ) -> float | None:
        """Calculate momentum score (12-1 month returns).

        Args:
            symbol: Ticker symbol
            as_of_date: Date to calculate momentum as of
            lookback_months: Number of months to look back
            skip_months: Number of recent months to skip

        Returns:
            Momentum score as float, or None if insufficient data
        """
        file_path = self.parquet_path / "prices" / f"{symbol}.parquet"

        if not file_path.exists():
            return None

        query = f"""
            WITH ranked_prices AS (
                SELECT
                    date,
                    adj_close,
                    ROW_NUMBER() OVER (ORDER BY date DESC) as rn
                FROM read_parquet('{file_path}')
                WHERE date <= '{as_of_date}'
            )
            SELECT
                (SELECT adj_close FROM ranked_prices WHERE rn = {skip_months * 21}) as recent_price,
                (SELECT adj_close FROM ranked_prices WHERE rn = {lookback_months * 21}) as old_price
        """

        result = self._conn.execute(query).fetchone()
        if result and result[0] and result[1]:
            recent_price, old_price = result
            return (recent_price - old_price) / old_price

        return None

    def get_moving_average(
        self,
        symbol: str,
        as_of_date: date,
        window_days: int = 200,
    ) -> float | None:
        """Calculate simple moving average.

        Args:
            symbol: Ticker symbol
            as_of_date: Date to calculate MA as of
            window_days: Number of trading days in window

        Returns:
            Moving average value, or None if insufficient data
        """
        file_path = self.parquet_path / "prices" / f"{symbol}.parquet"

        if not file_path.exists():
            return None

        query = f"""
            SELECT AVG(adj_close) as ma
            FROM (
                SELECT adj_close
                FROM read_parquet('{file_path}')
                WHERE date <= '{as_of_date}'
                ORDER BY date DESC
                LIMIT {window_days}
            )
        """

        result = self._conn.execute(query).fetchone()
        return result[0] if result and result[0] else None

    def get_universe_fundamentals(self, symbols: list[str]) -> pd.DataFrame:
        """Get fundamental data for a list of symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            DataFrame with fundamental metrics for all symbols
        """
        results = []
        for symbol in symbols:
            file_path = self.parquet_path / "fundamentals" / f"{symbol}.parquet"
            if file_path.exists():
                df = self._conn.execute(
                    f"SELECT * FROM read_parquet('{file_path}')"
                ).fetchdf()
                if not df.empty:
                    results.append(df.iloc[0].to_dict())

        return pd.DataFrame(results) if results else pd.DataFrame()

    def close(self) -> None:
        """Close the DuckDB connection."""
        self._conn.close()
