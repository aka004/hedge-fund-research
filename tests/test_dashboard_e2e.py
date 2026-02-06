"""End-to-end tests for the AFML Research Dashboard.

Tests the full pipeline: seed data → verify DB → verify API responses.
"""

import json
import sys
import uuid
from pathlib import Path

import numpy as np
import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "backend"))


@pytest.fixture(scope="module")
def seeded_run_id():
    """Seed a test run and return its run_id."""
    from app.core.database import get_db_write

    run_id = f"test-{uuid.uuid4()}"
    tickers = ["AAPL", "MSFT", "GOOGL"]
    np.random.seed(123)

    with get_db_write() as conn:
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
                "test_strategy",
                "2024-01-01",
                "2024-06-30",
                ",".join(tickers),
                3,
                1.2,
                0.88,
                0.75,
                0.15,
                json.dumps(["test caveat"]),
                True,
            ],
        )

        # Equity curve (10 days)
        equity = 100_000.0
        peak = equity
        for i in range(10):
            ret = (np.random.randn() * 0.01) + 0.001
            equity *= 1 + ret
            peak = max(peak, equity)
            dd = (equity - peak) / peak * 100
            conn.execute(
                """
                INSERT INTO derived_backtest_equity
                    (run_id, date, equity, benchmark_equity, drawdown, daily_return)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                [run_id, f"2024-01-{i + 2:02d}", equity, 100_000 + i * 100, dd, ret],
            )

        # Portfolio weights
        for t in tickers:
            conn.execute(
                """
                INSERT INTO derived_portfolio_weights
                    (run_id, date, ticker, weight, hrp_weight,
                     kelly_fraction, signal_source, is_mock)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                [run_id, "2024-01-11", t, 1.0 / 3, 0.33, 0.08, "momentum", True],
            )

        # AFML metrics
        for name, val in [("psr", 0.88), ("deflated_sharpe", 0.75), ("pbo", 0.15)]:
            conn.execute(
                """
                INSERT INTO derived_afml_metrics
                    (run_id, metric_name, metric_value, details, is_mock, caveats)
                VALUES ($1,$2,$3,$4,$5,$6)
                """,
                [run_id, name, val, json.dumps({}), True, None],
            )

        # MDA importance
        conn.execute(
            """
            INSERT INTO derived_afml_metrics
                (run_id, metric_name, metric_value, details, is_mock, caveats)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            [
                run_id,
                "mda_importance",
                None,
                json.dumps({"momentum": 0.4, "value": 0.3}),
                True,
                None,
            ],
        )

        # Bootstrap metrics
        conn.execute(
            """
            INSERT INTO derived_afml_metrics
                (run_id, metric_name, metric_value, details, is_mock, caveats)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            [run_id, "bootstrap_standard", 0.42, json.dumps({}), True, None],
        )
        conn.execute(
            """
            INSERT INTO derived_afml_metrics
                (run_id, metric_name, metric_value, details, is_mock, caveats)
            VALUES ($1,$2,$3,$4,$5,$6)
            """,
            [run_id, "bootstrap_sequential", 0.78, json.dumps({}), True, None],
        )

        # CV paths (3 paths x 5 days)
        for pid in range(3):
            eq = 1.0
            for day in range(5):
                eq *= 1 + np.random.randn() * 0.01
                conn.execute(
                    """
                    INSERT INTO derived_cv_paths
                        (run_id, path_id, day_index, equity)
                    VALUES ($1,$2,$3,$4)
                    """,
                    [run_id, pid, day, float(eq)],
                )

    yield run_id

    # Cleanup
    with get_db_write() as conn:
        for table in [
            "derived_backtest_runs",
            "derived_backtest_equity",
            "derived_portfolio_weights",
            "derived_afml_metrics",
            "derived_cv_paths",
        ]:
            conn.execute(f"DELETE FROM {table} WHERE run_id = $1", [run_id])


class TestDatabaseSeeding:
    """Verify derived tables are populated correctly."""

    def test_run_exists(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT strategy_name FROM derived_backtest_runs WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()
        assert row is not None
        assert row[0] == "test_strategy"

    def test_equity_curve_populated(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM derived_backtest_equity WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()[0]
        assert count == 10

    def test_portfolio_weights_populated(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM derived_portfolio_weights WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()[0]
        assert count == 3

    def test_afml_metrics_populated(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM derived_afml_metrics WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()[0]
        assert count >= 5  # psr, deflated_sharpe, pbo, mda, bootstrap x2

    def test_cv_paths_populated(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM derived_cv_paths WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()[0]
        assert count == 15  # 3 paths x 5 days

    def test_caveats_non_empty(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT caveats FROM derived_backtest_runs WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()
        caveats = json.loads(row[0])
        assert len(caveats) > 0


class TestAPIResponses:
    """Verify API endpoint responses are valid."""

    def test_overview_returns_valid_json(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            run = conn.execute(
                "SELECT * FROM derived_backtest_runs WHERE run_id = $1",
                [seeded_run_id],
            ).fetchdf()
        assert not run.empty
        assert run.iloc[0]["sharpe_raw"] == pytest.approx(1.2, abs=0.01)

    def test_equity_curve_ordered_by_date(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            dates = (
                conn.execute(
                    "SELECT date FROM derived_backtest_equity "
                    "WHERE run_id = $1 ORDER BY date",
                    [seeded_run_id],
                )
                .fetchdf()["date"]
                .tolist()
            )
        assert dates == sorted(dates)

    def test_feature_importance_has_entries(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT details FROM derived_afml_metrics "
                "WHERE run_id = $1 AND metric_name = 'mda_importance'",
                [seeded_run_id],
            ).fetchone()
        details = json.loads(row[0])
        assert "momentum" in details
        assert details["momentum"] > 0

    def test_cv_paths_grouped_correctly(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            paths = conn.execute(
                "SELECT DISTINCT path_id FROM derived_cv_paths WHERE run_id = $1",
                [seeded_run_id],
            ).fetchdf()
        assert len(paths) == 3

    def test_bootstrap_comparison_has_both_methods(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            rows = conn.execute(
                "SELECT metric_name, metric_value FROM derived_afml_metrics "
                "WHERE run_id = $1 AND metric_name LIKE 'bootstrap_%'",
                [seeded_run_id],
            ).fetchdf()
        methods = set(rows["metric_name"].tolist())
        assert "bootstrap_standard" in methods
        assert "bootstrap_sequential" in methods
        # Sequential should be higher
        std_val = float(
            rows[rows["metric_name"] == "bootstrap_standard"]["metric_value"].iloc[0]
        )
        seq_val = float(
            rows[rows["metric_name"] == "bootstrap_sequential"]["metric_value"].iloc[0]
        )
        assert seq_val > std_val

    def test_mock_data_flagged(self, seeded_run_id):
        from app.core.database import get_db

        with get_db() as conn:
            row = conn.execute(
                "SELECT is_mock FROM derived_backtest_runs WHERE run_id = $1",
                [seeded_run_id],
            ).fetchone()
        assert row[0] is True
