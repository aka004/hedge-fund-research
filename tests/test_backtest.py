"""Tests for backtesting engine."""

from datetime import date

import pytest

from strategy.backtest.portfolio import (
    Portfolio,
    PortfolioManager,
    Position,
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
