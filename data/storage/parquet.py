"""Parquet-based data storage for cached market data."""

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class ParquetStorage:
    """Storage layer using Parquet files for efficient data persistence."""

    def __init__(self, base_path: Path) -> None:
        """Initialize Parquet storage.

        Args:
            base_path: Base directory for storing parquet files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_file_path(self, data_type: str, symbol: str) -> Path:
        """Get the file path for a specific data type and symbol."""
        type_dir = self.base_path / data_type
        type_dir.mkdir(parents=True, exist_ok=True)
        return type_dir / f"{symbol}.parquet"

    def save_prices(self, symbol: str, df: pd.DataFrame) -> None:
        """Save price data to parquet.

        Args:
            symbol: Ticker symbol
            df: DataFrame with price data
        """
        file_path = self._get_file_path("prices", symbol)

        # If file exists, merge with existing data
        if file_path.exists():
            existing_df = self.load_prices(symbol)
            if existing_df is not None:
                # Convert date columns to same type for merging
                df["date"] = pd.to_datetime(df["date"]).dt.date
                existing_df["date"] = pd.to_datetime(existing_df["date"]).dt.date

                # Merge and deduplicate
                combined = pd.concat([existing_df, df], ignore_index=True)
                combined = combined.drop_duplicates(subset=["date"], keep="last")
                combined = combined.sort_values("date").reset_index(drop=True)
                df = combined

        # Ensure date is datetime64 for proper parquet storage
        df_to_save = df.copy()
        df_to_save["date"] = pd.to_datetime(df_to_save["date"])

        # Sort by date and set as index for efficient queries
        df_to_save = df_to_save.sort_values("date").reset_index(drop=True)

        table = pa.Table.from_pandas(df_to_save, preserve_index=False)
        pq.write_table(table, file_path, compression="snappy")
        logger.info(f"Saved {len(df)} price records for {symbol}")

    def load_prices(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame | None:
        """Load price data from parquet.

        Args:
            symbol: Ticker symbol
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            DataFrame with price data, or None if not found
        """
        file_path = self._get_file_path("prices", symbol)
        if not file_path.exists():
            return None

        df = pq.read_table(file_path).to_pandas()
        df["date"] = pd.to_datetime(df["date"]).dt.date

        # Apply date filters
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]

        return df.reset_index(drop=True) if not df.empty else None

    def get_last_date(self, symbol: str) -> date | None:
        """Get the last date for which we have price data.

        Args:
            symbol: Ticker symbol

        Returns:
            Last date in storage, or None if no data exists
        """
        file_path = self._get_file_path("prices", symbol)
        if not file_path.exists():
            return None

        # Read only the date column for efficiency
        table = pq.read_table(file_path, columns=["date"])
        if table.num_rows == 0:
            return None

        df = table.to_pandas()
        last_date = pd.to_datetime(df["date"]).max()
        return last_date.date()

    def save_fundamentals(self, symbol: str, data: dict) -> None:
        """Save fundamental data to parquet.

        Args:
            symbol: Ticker symbol
            data: Dictionary of fundamental metrics
        """
        file_path = self._get_file_path("fundamentals", symbol)

        # Add timestamp
        data = data.copy()
        data["updated_at"] = pd.Timestamp.now().isoformat()

        df = pd.DataFrame([data])
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(table, file_path, compression="snappy")
        logger.info(f"Saved fundamentals for {symbol}")

    def load_fundamentals(self, symbol: str) -> dict | None:
        """Load fundamental data from parquet.

        Args:
            symbol: Ticker symbol

        Returns:
            Dictionary of fundamental metrics, or None if not found
        """
        file_path = self._get_file_path("fundamentals", symbol)
        if not file_path.exists():
            return None

        df = pq.read_table(file_path).to_pandas()
        if df.empty:
            return None

        return df.iloc[0].to_dict()

    def save_sentiment(self, symbol: str, data: dict) -> None:
        """Save sentiment data to parquet, appending to history.

        Args:
            symbol: Ticker symbol
            data: Dictionary of sentiment metrics
        """
        file_path = self._get_file_path("sentiment", symbol)

        new_df = pd.DataFrame([data])

        if file_path.exists():
            existing_df = pq.read_table(file_path).to_pandas()
            df = pd.concat([existing_df, new_df], ignore_index=True)
        else:
            df = new_df

        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(table, file_path, compression="snappy")
        logger.info(f"Saved sentiment data for {symbol}")

    def load_sentiment(self, symbol: str) -> pd.DataFrame | None:
        """Load sentiment history from parquet.

        Args:
            symbol: Ticker symbol

        Returns:
            DataFrame with sentiment history, or None if not found
        """
        file_path = self._get_file_path("sentiment", symbol)
        if not file_path.exists():
            return None

        df = pq.read_table(file_path).to_pandas()
        return df if not df.empty else None

    def list_symbols(self, data_type: str) -> list[str]:
        """List all symbols with cached data of a specific type.

        Args:
            data_type: Type of data (prices, fundamentals, sentiment)

        Returns:
            List of symbol names
        """
        type_dir = self.base_path / data_type
        if not type_dir.exists():
            return []

        return [f.stem for f in type_dir.glob("*.parquet")]

    def delete_symbol(self, symbol: str, data_type: str | None = None) -> None:
        """Delete cached data for a symbol.

        Args:
            symbol: Ticker symbol
            data_type: Specific data type to delete, or None for all
        """
        types = [data_type] if data_type else ["prices", "fundamentals", "sentiment"]

        for dt in types:
            file_path = self._get_file_path(dt, symbol)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted {dt} data for {symbol}")
