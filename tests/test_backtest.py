"""Tests for backtesting engine."""

from datetime import date

import pandas as pd
import pytest

from analysis.metrics import calculate_metrics
from strategy.backtest.portfolio import (
    Portfolio,
    PortfolioManager,
    Position,
    RoundTripTrade,
    Trade,
    TransactionCosts,
)


class TestPosition:
    """Tests for Position."""

    def test_position_creation(self):
        pos = Position(
            symbol="AAPL",
            shares=100,
            entry_price=150.0,
            entry_date=date(2024, 1, 1),
            current_price=160.0,
        )

        assert pos.symbol == "AAPL"
        assert pos.shares == 100
        assert pos.market_value == 16000.0
        assert pos.cost_basis == 15000.0
        assert pos.unrealized_pnl == 1000.0
        assert pos.unrealized_return == pytest.approx(1000 / 15000, rel=0.001)


class TestTrade:
    """Tests for Trade."""

    def test_buy_trade(self):
        trade = Trade(
            symbol="AAPL",
            date=date(2024, 1, 1),
            side="buy",
            shares=100,
            price=150.0,
            commission=5.0,
            slippage=1.5,
        )

        assert trade.gross_value == 15000.0
        assert trade.net_value == 15006.5  # gross + costs for buy

    def test_sell_trade(self):
        trade = Trade(
            symbol="AAPL",
            date=date(2024, 1, 1),
            side="sell",
            shares=100,
            price=160.0,
            commission=5.0,
            slippage=1.5,
        )

        assert trade.gross_value == 16000.0
        assert trade.net_value == 15993.5  # gross - costs for sell


class TestTransactionCosts:
    """Tests for TransactionCosts."""

    def test_default_costs(self):
        costs = TransactionCosts()
        commission, slippage = costs.calculate(100, 150.0)

        assert commission == 0.0
        assert slippage == 15.0  # 10 bps on $15,000

    def test_custom_costs(self):
        costs = TransactionCosts(
            commission_per_share=0.01,
            slippage_bps=5.0,
        )
        commission, slippage = costs.calculate(100, 150.0)

        assert commission == 1.0
        assert slippage == 7.5  # 5 bps on $15,000


class TestPortfolio:
    """Tests for Portfolio."""

    def test_empty_portfolio(self):
        portfolio = Portfolio(cash=100000.0)

        assert portfolio.equity == 100000.0
        assert portfolio.position_count == 0

    def test_portfolio_with_positions(self):
        portfolio = Portfolio(
            cash=50000.0,
            positions={
                "AAPL": Position("AAPL", 100, 150.0, date(2024, 1, 1), 160.0),
            },
        )

        assert portfolio.equity == 66000.0  # 50000 + 16000
        assert portfolio.position_count == 1

    def test_get_weights(self):
        portfolio = Portfolio(
            cash=50000.0,
            positions={
                "AAPL": Position("AAPL", 100, 150.0, date(2024, 1, 1), 160.0),
            },
        )

        weights = portfolio.get_weights()
        assert weights["AAPL"] == pytest.approx(16000 / 66000, rel=0.001)


class TestPortfolioManager:
    """Tests for PortfolioManager."""

    def test_buy_order(self):
        manager = PortfolioManager(100000.0)

        trade = manager.buy("AAPL", 100, 150.0, date(2024, 1, 1))

        assert trade is not None
        assert trade.symbol == "AAPL"
        assert trade.shares == 100
        assert "AAPL" in manager.portfolio.positions

    def test_buy_insufficient_cash(self):
        manager = PortfolioManager(1000.0)

        trade = manager.buy("AAPL", 100, 150.0, date(2024, 1, 1))

        assert trade is None

    def test_sell_order(self):
        manager = PortfolioManager(100000.0)
        manager.buy("AAPL", 100, 150.0, date(2024, 1, 1))

        trade = manager.sell("AAPL", 50, 160.0, date(2024, 1, 2))

        assert trade is not None
        assert trade.shares == 50
        assert manager.portfolio.positions["AAPL"].shares == 50

    def test_sell_all_closes_position(self):
        manager = PortfolioManager(100000.0)
        manager.buy("AAPL", 100, 150.0, date(2024, 1, 1))

        manager.sell("AAPL", 100, 160.0, date(2024, 1, 2))

        assert "AAPL" not in manager.portfolio.positions

    def test_sell_nonexistent_position(self):
        manager = PortfolioManager(100000.0)

        trade = manager.sell("AAPL", 100, 150.0, date(2024, 1, 1))

        assert trade is None

    def test_close_position(self):
        manager = PortfolioManager(100000.0)
        manager.buy("AAPL", 100, 150.0, date(2024, 1, 1))

        trade = manager.close_position("AAPL", 160.0, date(2024, 1, 2))

        assert trade is not None
        assert trade.shares == 100
        assert "AAPL" not in manager.portfolio.positions

    def test_rebalance_to_targets(self):
        manager = PortfolioManager(100000.0)

        targets = {"AAPL": 0.5, "GOOGL": 0.3}
        prices = {"AAPL": 150.0, "GOOGL": 100.0}

        trades = manager.rebalance_to_targets(targets, prices, date(2024, 1, 1))

        assert len(trades) == 2

        # Check approximate weights
        manager.portfolio.update_prices(prices)
        weights = manager.portfolio.get_weights()

        assert weights["AAPL"] == pytest.approx(0.5, rel=0.05)
        assert weights["GOOGL"] == pytest.approx(0.3, rel=0.05)


class TestGetReturnsSeries:
    """Tests for PortfolioManager.get_returns_series (Task 1.6)."""

    def test_empty_returns(self):
        manager = PortfolioManager(100000.0)
        result = manager.get_returns_series()
        assert result.empty

    def test_single_snapshot_returns_empty(self):
        manager = PortfolioManager(100000.0)
        manager.record_snapshot(date(2024, 1, 1))
        result = manager.get_returns_series()
        assert result.empty

    def test_returns_from_snapshots(self):
        manager = PortfolioManager(100000.0)
        manager.record_snapshot(date(2024, 1, 1))

        # Simulate a price move: buy AAPL, price goes up
        manager.buy("AAPL", 100, 150.0, date(2024, 1, 1))
        manager.portfolio.update_prices({"AAPL": 160.0})
        manager.record_snapshot(date(2024, 2, 1))

        result = manager.get_returns_series()
        assert len(result) == 1
        # Equity went from 100000 to (cash + 100*160)
        expected_equity = manager.portfolio.equity
        expected_return = (expected_equity - 100000.0) / 100000.0
        assert result.iloc[0] == pytest.approx(expected_return, rel=0.01)


class TestRoundTripTrade:
    """Tests for RoundTripTrade lifecycle fields."""

    def test_round_trip_properties(self):
        rt = RoundTripTrade(
            symbol="AAPL",
            entry_date=date(2024, 1, 1),
            entry_price=150.0,
            entry_reason="signal_rebalance",
            exit_date=date(2024, 1, 22),
            exit_price=165.0,
            exit_reason="profit_target",
            shares=100,
        )

        assert rt.holding_days == 21
        assert rt.pnl == 1500.0
        assert rt.return_pct == pytest.approx(0.10, rel=0.001)

    def test_open_trade_returns_none(self):
        rt = RoundTripTrade(
            symbol="AAPL",
            entry_date=date(2024, 1, 1),
            entry_price=150.0,
            entry_reason="signal_rebalance",
            shares=100,
        )

        assert rt.holding_days is None
        assert rt.pnl is None
        assert rt.return_pct is None


class TestCalculateMetricsWithTradeLog:
    """Tests for calculate_metrics with trade_log DataFrame (Task 1.8)."""

    def test_trade_log_preferred_over_legacy(self):
        returns = pd.Series([0.01, -0.005, 0.02, 0.01, -0.01])
        trade_log = pd.DataFrame(
            [
                {
                    "symbol": "AAPL",
                    "pnl": 500.0,
                    "return_pct": 0.05,
                    "holding_days": 10,
                    "max_favorable": 0.08,
                    "max_adverse": -0.02,
                    "exit_reason": "profit_target",
                },
                {
                    "symbol": "GOOGL",
                    "pnl": -200.0,
                    "return_pct": -0.03,
                    "holding_days": 21,
                    "max_favorable": 0.01,
                    "max_adverse": -0.05,
                    "exit_reason": "stop_loss",
                },
            ]
        )

        metrics = calculate_metrics(returns, trade_log=trade_log)
        assert metrics.total_trades == 2
        assert metrics.win_rate == 0.5
        assert metrics.profit_factor == 500.0 / 200.0

    def test_empty_trade_log_zero_trades(self):
        returns = pd.Series([0.01, -0.005, 0.02])
        metrics = calculate_metrics(returns, trade_log=pd.DataFrame())
        assert metrics.total_trades == 0
        assert metrics.win_rate == 0.0
