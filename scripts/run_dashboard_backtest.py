"""CLI runner for dashboard backtest validation."""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.services.backtest_runner import DashboardBacktestRunner


def main():
    parser = argparse.ArgumentParser(
        description="Run dashboard backtest with AFML validation"
    )
    parser.add_argument(
        "--universe",
        nargs="+",
        default=["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
        help="Ticker symbols",
    )
    parser.add_argument(
        "--start-date",
        default="2023-01-01",
        help="Start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end-date",
        default="2024-12-31",
        help="End date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--strategy",
        default="momentum_value",
        help="Strategy name",
    )
    parser.add_argument(
        "--n-strategies",
        type=int,
        default=1,
        help="Number of strategies tested (for PSR deflation)",
    )

    args = parser.parse_args()

    runner = DashboardBacktestRunner()
    result = runner.run_full_validation(
        universe=args.universe,
        start_date=args.start_date,
        end_date=args.end_date,
        strategy_name=args.strategy,
        n_strategies_tested=args.n_strategies,
    )

    print(f"\nRun ID: {result.run_id}")
    print(f"Raw Sharpe: {result.raw_metrics['sharpe_raw']:.4f}")
    print(f"PSR: {result.afml_metrics['psr']['value']:.4f}")
    print(f"PBO: {result.afml_metrics['pbo']['value']}")
    print("\nCaveats:")
    for c in result.caveats:
        print(f"  - {c}")
    print("\nComparison:")
    for k, v in result.comparison.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
