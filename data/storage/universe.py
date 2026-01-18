"""Universe management for stock selection."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# S&P 500 symbols as of early 2024 (simplified list - normally would fetch live)
SP500_SYMBOLS = [
    "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
    "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK.B", "C",
    "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS",
    "CVX", "DE", "DHR", "DIS", "DOW", "DUK", "EMR", "EXC", "F", "FDX",
    "GD", "GE", "GILD", "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM",
    "INTC", "INTU", "ISRG", "JNJ", "JPM", "KHC", "KO", "LIN", "LLY", "LMT",
    "LOW", "MA", "MCD", "MDLZ", "MDT", "MET", "META", "MMM", "MO", "MRK",
    "MS", "MSFT", "NEE", "NFLX", "NKE", "NOW", "NVDA", "ORCL", "PEP", "PFE",
    "PG", "PM", "PYPL", "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T",
    "TGT", "TMO", "TMUS", "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V",
    "VZ", "WFC", "WMT", "XOM",
]


class UniverseManager:
    """Manages stock universes for backtesting."""

    def __init__(self, storage_path: Path) -> None:
        """Initialize universe manager.

        Args:
            storage_path: Path to store universe data
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def get_sp500_symbols(self) -> list[str]:
        """Get current S&P 500 symbols.

        Returns:
            List of S&P 500 ticker symbols
        """
        return SP500_SYMBOLS.copy()

    def save_custom_universe(self, name: str, symbols: list[str]) -> None:
        """Save a custom universe.

        Args:
            name: Universe name
            symbols: List of ticker symbols
        """
        file_path = self.storage_path / f"{name}.csv"
        df = pd.DataFrame({"symbol": symbols})
        df.to_csv(file_path, index=False)
        logger.info(f"Saved universe '{name}' with {len(symbols)} symbols")

    def load_universe(self, name: str) -> list[str]:
        """Load a universe by name.

        Args:
            name: Universe name (use 'sp500' for S&P 500)

        Returns:
            List of ticker symbols
        """
        if name.lower() == "sp500":
            return self.get_sp500_symbols()

        file_path = self.storage_path / f"{name}.csv"
        if not file_path.exists():
            raise ValueError(f"Universe '{name}' not found")

        df = pd.read_csv(file_path)
        return df["symbol"].tolist()

    def list_universes(self) -> list[str]:
        """List all available universes.

        Returns:
            List of universe names
        """
        universes = ["sp500"]  # Built-in
        universes.extend(f.stem for f in self.storage_path.glob("*.csv"))
        return universes

    def filter_universe(
        self,
        symbols: list[str],
        min_market_cap: float | None = None,
        sectors: list[str] | None = None,
        exclude_symbols: list[str] | None = None,
    ) -> list[str]:
        """Filter a universe based on criteria.

        Args:
            symbols: Input symbol list
            min_market_cap: Minimum market cap filter
            sectors: List of sectors to include
            exclude_symbols: Symbols to exclude

        Returns:
            Filtered list of symbols
        """
        result = symbols.copy()

        if exclude_symbols:
            result = [s for s in result if s not in exclude_symbols]

        # Note: market_cap and sector filtering would require fundamental data
        # This is a placeholder for the interface
        if min_market_cap or sectors:
            logger.warning(
                "Market cap and sector filtering requires fundamental data to be loaded"
            )

        return result
