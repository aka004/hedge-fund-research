"""Seed dashboard derived tables with synthetic data for dev/demo.

Populates all 8 derived_* tables with realistic mock data so the
dashboard UI can be tested without running a full backtest.
"""

import json
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))

from app.core.database import get_db_write


def seed():
    run_id = str(uuid.uuid4())
    strategy = "momentum_value_seed"
    start = "2023-01-03"
    end = "2024-12-31"
    tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]
    np.random.seed(42)

    print(f"Seeding run_id={run_id}")

    with get_db_write() as conn:
        # 1. derived_backtest_runs
        conn.execute(
            """
            INSERT INTO derived_backtest_runs
                (run_id, strategy_name, start_date, end_date,
                 universe, n_assets, sharpe_raw, psr,
                 deflated_sharpe, pbo, caveats, is_mock)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
            """,
            [
                run_id,
                strategy,
                start,
                end,
                ",".join(tickers),
                len(tickers),
                1.47,
                0.91,
                0.84,
                0.12,
                json.dumps(["Seeded demo data", "Not from real backtest"]),
                True,
            ],
        )
        print("  [+] derived_backtest_runs")

        # 2. derived_backtest_equity (504 trading days)
        dates = pd.bdate_range(start, end)
        equity = 100_000.0
        peak = equity
        rows = []
        for i, d in enumerate(dates):
            daily_ret = (np.random.randn() * 0.012) + 0.0003
            equity *= 1 + daily_ret
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100
            bench = 100_000 * (1 + 0.00035) ** i
            rows.append([run_id, d.date(), equity, bench, dd, daily_ret])

        for r in rows:
            conn.execute(
                """
                INSERT INTO derived_backtest_equity
                    (run_id, date, equity, benchmark_equity, drawdown, daily_return)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                r,
            )
        print(f"  [+] derived_backtest_equity ({len(rows)} rows)")

        # 3. derived_portfolio_weights
        hrp_w = np.random.dirichlet(np.ones(len(tickers)))
        kelly_f = np.random.uniform(0.04, 0.14, len(tickers))
        last_date = dates[-1].date()

        for i, t in enumerate(tickers):
            conn.execute(
                """
                INSERT INTO derived_portfolio_weights
                    (run_id, date, ticker, weight, hrp_weight,
                     kelly_fraction, signal_source, is_mock)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                [
                    run_id,
                    last_date,
                    t,
                    1.0 / len(tickers),
                    float(hrp_w[i]),
                    float(kelly_f[i]),
                    "momentum+value",
                    True,
                ],
            )
        print(f"  [+] derived_portfolio_weights ({len(tickers)} tickers)")

        # 4. derived_afml_metrics
        metrics = {
            "psr": (0.91, json.dumps({"sharpe": 1.47, "n_observations": 504})),
            "deflated_sharpe": (0.84, json.dumps({"n_strategies_tested": 1})),
            "pbo": (0.12, json.dumps({"n_paths": 15})),
            "mda_importance": (
                None,
                json.dumps(
                    {
                        "momentum": 0.34,
                        "value": 0.22,
                        "volatility": 0.18,
                        "volume_ma": 0.12,
                    }
                ),
            ),
            "bootstrap_standard": (0.42, json.dumps({})),
            "bootstrap_sequential": (0.78, json.dumps({})),
        }
        for name, (val, details) in metrics.items():
            conn.execute(
                """
                INSERT INTO derived_afml_metrics
                    (run_id, metric_name, metric_value, details, is_mock, caveats)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                [run_id, name, val, details, True, None],
            )
        print(f"  [+] derived_afml_metrics ({len(metrics)} metrics)")

        # 5. derived_cv_paths (15 paths x 84 days)
        n_paths = 15
        n_days = 84
        for pid in range(n_paths):
            eq = 1.0
            for day in range(n_days):
                eq *= 1 + (np.random.randn() * 0.015 + 0.001 * (pid % 5))
                conn.execute(
                    """
                    INSERT INTO derived_cv_paths
                        (run_id, path_id, day_index, equity)
                    VALUES ($1,$2,$3,$4)
                    """,
                    [run_id, pid, day, float(eq)],
                )
        print(f"  [+] derived_cv_paths ({n_paths} paths x {n_days} days)")

        # 6. derived_regime_history
        regime_dates = pd.bdate_range("2023-06-01", end)
        regimes = [
            "bull",
            "bull",
            "volatile",
            "bear",
            "bull",
            "bull",
            "volatile",
            "bull",
        ]
        for i, d in enumerate(regime_dates):
            regime = regimes[i % len(regimes)]
            ma_200 = 150.0 + i * 0.05
            price = ma_200 * (1 + np.random.randn() * 0.03)
            dist = (price - ma_200) / ma_200 * 100
            conn.execute(
                """
                INSERT OR REPLACE INTO derived_regime_history
                    (date, regime, ma_200, price, distance_pct,
                     cusum_value, days_in_regime)
                VALUES ($1,$2,$3,$4,$5,$6,$7)
                """,
                [
                    d.date(),
                    regime,
                    ma_200,
                    price,
                    dist,
                    np.random.randn() * 0.5,
                    i % 30 + 1,
                ],
            )
        print(f"  [+] derived_regime_history ({len(regime_dates)} rows)")

    print(f"\nDone! Run ID: {run_id}")
    print("Start the backend and navigate to /dashboard to see the data.")


if __name__ == "__main__":
    seed()
