"""
Persistence layer for backtest results and AFML metrics.

Writes derived data into DuckDB tables created by
scripts/migrate_derived_tables.py.
"""

import json
import uuid

import numpy as np
import pandas as pd

from app.core.database import get_db, get_db_write


class BacktestPersistence:
    """Save and retrieve backtest runs and their associated data."""

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def save_run(
        self,
        result: dict,
        strategy_name: str,
        afml_metrics: dict,
        universe: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> str:
        """Save backtest run metadata. Returns run_id (UUID)."""
        run_id = str(uuid.uuid4())
        with get_db_write() as conn:
            conn.execute(
                """
                INSERT INTO derived_backtest_runs (
                    run_id, strategy_name, start_date, end_date,
                    universe, n_assets, sharpe_raw, psr,
                    deflated_sharpe, pbo, caveats, is_mock
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
                """,
                [
                    run_id,
                    strategy_name,
                    start_date or None,
                    end_date or None,
                    universe,
                    result.get("n_assets", 0),
                    result.get("sharpe_raw"),
                    afml_metrics.get("psr"),
                    afml_metrics.get("deflated_sharpe"),
                    afml_metrics.get("pbo"),
                    json.dumps(afml_metrics.get("caveats", [])),
                    result.get("is_mock", False),
                ],
            )
        return run_id

    def save_equity_curve(self, run_id: str, equity_df: pd.DataFrame) -> None:
        """Save daily equity curve.

        DataFrame expected columns:
            date, equity, benchmark_equity, drawdown, daily_return
        """
        with get_db_write() as conn:
            for row in equity_df.itertuples(index=False):
                conn.execute(
                    """
                    INSERT INTO derived_backtest_equity
                        (run_id, date, equity, benchmark_equity,
                         drawdown, daily_return)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    [
                        run_id,
                        row.date,
                        row.equity,
                        row.benchmark_equity,
                        row.drawdown,
                        row.daily_return,
                    ],
                )

    def save_trades(self, run_id: str, trades_df: pd.DataFrame) -> None:
        """Save trade log."""
        with get_db_write() as conn:
            for row in trades_df.itertuples(index=False):
                trade_id = str(uuid.uuid4())
                conn.execute(
                    """
                    INSERT INTO derived_backtest_trades
                        (run_id, trade_id, date, ticker, side,
                         shares, price, commission)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    [
                        run_id,
                        trade_id,
                        row.date,
                        row.ticker,
                        row.side,
                        row.shares,
                        row.price,
                        row.commission,
                    ],
                )

    def save_signals(self, run_id: str, signals_df: pd.DataFrame) -> None:
        """Save signal output."""
        with get_db_write() as conn:
            for row in signals_df.itertuples(index=False):
                metadata = getattr(row, "metadata", None)
                if metadata and not isinstance(metadata, str):
                    metadata = json.dumps(metadata)
                conn.execute(
                    """
                    INSERT INTO derived_signals
                        (run_id, date, ticker, signal_name,
                         score, rank, metadata)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                    """,
                    [
                        run_id,
                        row.date,
                        row.ticker,
                        row.signal_name,
                        row.score,
                        row.rank,
                        metadata,
                    ],
                )

    def save_portfolio_weights(self, run_id: str, weights_df: pd.DataFrame) -> None:
        """Save portfolio weights with HRP/Kelly data."""
        with get_db_write() as conn:
            for row in weights_df.itertuples(index=False):
                conn.execute(
                    """
                    INSERT INTO derived_portfolio_weights
                        (run_id, date, ticker, weight,
                         hrp_weight, kelly_fraction,
                         signal_source, is_mock)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                    """,
                    [
                        run_id,
                        row.date,
                        row.ticker,
                        row.weight,
                        getattr(row, "hrp_weight", None),
                        getattr(row, "kelly_fraction", None),
                        getattr(row, "signal_source", None),
                        getattr(row, "is_mock", False),
                    ],
                )

    def save_afml_metrics(self, run_id: str, metrics: dict) -> None:
        """Save individual AFML metric results.

        metrics is a dict like:
            {"psr": {"value": 0.97, "details": {...}, "caveats": [...]}, ...}
        """
        with get_db_write() as conn:
            for name, data in metrics.items():
                if isinstance(data, dict):
                    value = data.get("value")
                    details = json.dumps(data.get("details", {}))
                    is_mock = data.get("is_mock", False)
                    caveats = json.dumps(data.get("caveats", []))
                else:
                    value = float(data) if data is not None else None
                    details = None
                    is_mock = False
                    caveats = None
                conn.execute(
                    """
                    INSERT INTO derived_afml_metrics
                        (run_id, metric_name, metric_value,
                         details, is_mock, caveats)
                    VALUES ($1,$2,$3,$4,$5,$6)
                    """,
                    [run_id, name, value, details, is_mock, caveats],
                )

    def save_cv_paths(self, run_id: str, paths: list) -> None:
        """Save CPCV equity paths.

        paths: list of numpy arrays, one per CV path.
        """
        with get_db_write() as conn:
            for path_id, path_array in enumerate(paths):
                arr = np.asarray(path_array)
                for day_index, equity in enumerate(arr):
                    conn.execute(
                        """
                        INSERT INTO derived_cv_paths
                            (run_id, path_id, day_index, equity)
                        VALUES ($1,$2,$3,$4)
                        """,
                        [run_id, path_id, day_index, float(equity)],
                    )

    def save_regime_history(self, regime_signal, prices: pd.Series) -> None:
        """Save regime timeline from a RegimeSignal object.

        regime_signal: object with .regimes DataFrame containing
            date, regime, ma_200, price, distance_pct,
            cusum_value, days_in_regime columns.
        """
        df = regime_signal.regimes
        with get_db_write() as conn:
            for row in df.itertuples(index=False):
                conn.execute(
                    """
                    INSERT OR REPLACE INTO derived_regime_history
                        (date, regime, ma_200, price,
                         distance_pct, cusum_value, days_in_regime)
                    VALUES ($1,$2,$3,$4,$5,$6,$7)
                    """,
                    [
                        row.date,
                        row.regime,
                        row.ma_200,
                        row.price,
                        row.distance_pct,
                        getattr(row, "cusum_value", None),
                        getattr(row, "days_in_regime", None),
                    ],
                )

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_latest_run_id(self) -> str | None:
        """Get the most recent run_id."""
        with get_db() as conn:
            result = conn.execute(
                """
                SELECT run_id FROM derived_backtest_runs
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
            return result[0] if result else None

    def get_run(self, run_id: str) -> dict | None:
        """Get run metadata by run_id."""
        with get_db() as conn:
            result = conn.execute(
                "SELECT * FROM derived_backtest_runs WHERE run_id = $1",
                [run_id],
            ).fetchdf()
            if result.empty:
                return None
            return result.to_dict("records")[0]
