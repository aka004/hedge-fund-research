"""Storage for politician trading transactions from SEC Form 4 filings."""

import logging
from datetime import date
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


class PoliticianTradeStorage:
    """Storage layer for politician trade transactions using Parquet files."""

    def __init__(self, base_path: Path) -> None:
        """Initialize politician trade storage.

        Args:
            base_path: Base directory for storing parquet files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.trades_dir = self.base_path / "politician_trades"
        self.trades_dir.mkdir(parents=True, exist_ok=True)

    def _get_politician_dir(self, politician_name: str) -> Path:
        """Get directory path for a politician's trades."""
        # Sanitize politician name for filesystem
        safe_name = politician_name.replace(" ", "_").replace("/", "_")
        politician_dir = self.trades_dir / safe_name
        politician_dir.mkdir(parents=True, exist_ok=True)
        return politician_dir

    def _get_file_path(self, politician_name: str, symbol: str | None = None) -> Path:
        """Get file path for politician trades.
        
        Args:
            politician_name: Name of politician
            symbol: Optional symbol to get specific file, or None for all trades
        """
        politician_dir = self._get_politician_dir(politician_name)
        
        if symbol:
            return politician_dir / f"{symbol}.parquet"
        else:
            return politician_dir / "all_trades.parquet"

    def save_trades(
        self,
        politician_name: str,
        trades_df: pd.DataFrame,
        symbol: str | None = None,
    ) -> None:
        """Save politician trades to parquet.

        Args:
            politician_name: Name of politician
            trades_df: DataFrame with trade transactions
            symbol: Optional symbol to save to symbol-specific file
        """
        if trades_df.empty:
            logger.warning(f"No trades to save for {politician_name}")
            return

        file_path = self._get_file_path(politician_name, symbol)

        # Ensure required columns exist
        required_columns = [
            "politician_name",
            "cik",
            "transaction_date",
            "filing_date",
            "disclosure_date",
            "symbol",
        ]
        
        for col in required_columns:
            if col not in trades_df.columns:
                if col == "politician_name":
                    trades_df["politician_name"] = politician_name
                else:
                    logger.warning(f"Missing column {col} in trades DataFrame")

        # Convert date columns to datetime
        date_columns = ["transaction_date", "filing_date", "disclosure_date"]
        for col in date_columns:
            if col in trades_df.columns:
                trades_df[col] = pd.to_datetime(trades_df[col]).dt.date

        # If file exists, merge with existing data
        if file_path.exists():
            existing_df = self.load_trades(politician_name, symbol)
            if existing_df is not None and not existing_df.empty:
                # Merge and deduplicate
                combined = pd.concat([existing_df, trades_df], ignore_index=True)
                
                # Deduplicate by transaction_date, symbol, and shares
                dedup_cols = ["transaction_date", "symbol", "shares"]
                if all(col in combined.columns for col in dedup_cols):
                    combined = combined.drop_duplicates(
                        subset=dedup_cols, keep="last"
                    )
                
                combined = combined.sort_values("transaction_date", ascending=False)
                trades_df = combined

        # Convert dates to datetime for parquet storage
        df_to_save = trades_df.copy()
        date_columns_for_parquet = ["transaction_date", "filing_date", "disclosure_date"]
        for col in date_columns_for_parquet:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col])

        # Sort by transaction date
        if "transaction_date" in df_to_save.columns:
            df_to_save = df_to_save.sort_values("transaction_date", ascending=False)

        table = pa.Table.from_pandas(df_to_save, preserve_index=False)
        pq.write_table(table, file_path, compression="snappy")
        
        logger.info(
            f"Saved {len(trades_df)} trades for {politician_name}"
            + (f" (symbol: {symbol})" if symbol else "")
        )

    def load_trades(
        self,
        politician_name: str,
        symbol: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame | None:
        """Load politician trades from parquet.

        Args:
            politician_name: Name of politician
            symbol: Optional symbol to filter by
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            DataFrame with trades, or None if not found
        """
        file_path = self._get_file_path(politician_name, symbol)
        
        if not file_path.exists():
            return None

        df = pq.read_table(file_path).to_pandas()
        
        # Convert date columns back to date
        date_columns = ["transaction_date", "filing_date", "disclosure_date"]
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col]).dt.date

        # Apply date filters
        if start_date and "transaction_date" in df.columns:
            df = df[df["transaction_date"] >= start_date]
        if end_date and "transaction_date" in df.columns:
            df = df[df["transaction_date"] <= end_date]

        # Apply symbol filter if specified
        if symbol and "symbol" in df.columns:
            df = df[df["symbol"] == symbol]

        return df.reset_index(drop=True) if not df.empty else None

    def list_politicians(self) -> list[str]:
        """List all politicians with stored trades.

        Returns:
            List of politician names
        """
        if not self.trades_dir.exists():
            return []

        politicians = []
        for politician_dir in self.trades_dir.iterdir():
            if politician_dir.is_dir():
                # Convert back from filesystem-safe name
                politician_name = politician_dir.name.replace("_", " ")
                politicians.append(politician_name)

        return sorted(politicians)

    def get_all_trades(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> pd.DataFrame:
        """Get all trades from all politicians.

        Args:
            start_date: Optional start date filter
            end_date: Optional end date filter

        Returns:
            DataFrame with all trades
        """
        politicians = self.list_politicians()
        
        all_trades = []
        for politician in politicians:
            trades = self.load_trades(politician, start_date=start_date, end_date=end_date)
            if trades is not None and not trades.empty:
                all_trades.append(trades)

        if not all_trades:
            return pd.DataFrame()

        result = pd.concat(all_trades, ignore_index=True)
        
        # Sort by transaction date
        if "transaction_date" in result.columns:
            result = result.sort_values("transaction_date", ascending=False)

        return result
