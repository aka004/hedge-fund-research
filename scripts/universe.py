"""
Universe registry — per-universe paths, benchmark, and history file.

Usage:
    from scripts.universe import get_universe_config, BENCHMARK_BY_UNIVERSE

    cfg = get_universe_config("sp500")
    prices_dir = cfg.prices_dir       # Path to parquet prices directory
    benchmark  = cfg.benchmark        # "SPY" or "IWM"
    history    = cfg.history_path     # Path to alpha_gpt_history_<name>.json
    tickers    = cfg.ticker_list_path # Path to <name>.txt universe file (may not exist yet)
"""

from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import STORAGE_PATH

PARQUET_BASE = STORAGE_PATH / "parquet"
HISTORY_BASE = STORAGE_PATH
UNIVERSE_DIR = Path(__file__).parent.parent / "data" / "universes"


BENCHMARK_BY_UNIVERSE: dict[str, str] = {
    "sp500": "SPY",
    "russell2000_tech": "IWM",
}


@dataclass
class UniverseConfig:
    name: str
    benchmark: str
    prices_dir: Path       # where OHLCV parquets live
    history_path: Path     # universe-scoped history JSON
    ticker_list_path: Path # text file of tickers (one per line)


_CONFIGS: dict[str, UniverseConfig] = {
    "sp500": UniverseConfig(
        name="sp500",
        benchmark="SPY",
        prices_dir=PARQUET_BASE / "prices",
        history_path=HISTORY_BASE / "alpha_gpt_history_sp500.json",
        ticker_list_path=UNIVERSE_DIR / "sp500.txt",
    ),
    "russell2000_tech": UniverseConfig(
        name="russell2000_tech",
        benchmark="IWM",
        prices_dir=PARQUET_BASE / "prices_russell2000",
        history_path=HISTORY_BASE / "alpha_gpt_history_russell2000_tech.json",
        ticker_list_path=UNIVERSE_DIR / "russell2000_tech.txt",
    ),
}


def get_universe_config(name: str) -> UniverseConfig:
    """Return UniverseConfig for the given universe name.

    Raises KeyError for unknown names.
    """
    if name not in _CONFIGS:
        raise KeyError(
            f"Unknown universe '{name}'. Available: {list(_CONFIGS)}"
        )
    return _CONFIGS[name]
