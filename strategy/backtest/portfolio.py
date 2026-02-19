"""Portfolio management for backtesting."""

from dataclasses import dataclass, field
from datetime import date

import pandas as pd


@dataclass
class Position:
    """Represents a position in a single stock."""

    symbol: str
    shares: float
    entry_price: float
    entry_date: date
    current_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.shares * self.entry_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_return(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return self.unrealized_pnl / self.cost_basis


@dataclass
class Trade:
    """Represents a single trade execution."""

    symbol: str
    date: date
    side: str  # "buy" or "sell"
    shares: float
    price: float
    commission: float = 0.0
    slippage: float = 0.0

    @property
    def gross_value(self) -> float:
        return self.shares * self.price

    @property
    def net_value(self) -> float:
        """Net value including costs."""
        costs = self.commission + self.slippage
        if self.side == "buy":
            return self.gross_value + costs
        else:
            return self.gross_value - costs


@dataclass
class RoundTripTrade:
    """Tracks full lifecycle of a position from entry to exit."""

    symbol: str
    entry_date: date
    entry_price: float
    entry_reason: str  # "signal_rebalance" | "cusum_event" (Phase 2)
    exit_date: date | None = None
    exit_price: float | None = None
    exit_reason: str | None = (
        None  # "profit_target" | "stop_loss" | "timeout" | "rebalance_out"
    )
    shares: float = 0.0
    max_favorable: float = 0.0  # best unrealized return (MFE)
    max_adverse: float = 0.0  # worst unrealized return (MAE)

    @property
    def holding_days(self) -> int | None:
        """Number of calendar days held."""
        if self.exit_date is None:
            return None
        return (self.exit_date - self.entry_date).days

    @property
    def pnl(self) -> float | None:
        """Profit/loss in dollar terms."""
        if self.exit_price is None:
            return None
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def return_pct(self) -> float | None:
        """Return as a percentage of entry price."""
        if self.exit_price is None or self.entry_price == 0:
            return None
        return (self.exit_price - self.entry_price) / self.entry_price


@dataclass
class Portfolio:
    """Manages a portfolio of positions."""

    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    trade_history: list[Trade] = field(default_factory=list)

    @property
    def equity(self) -> float:
        """Total portfolio value (cash + positions)."""
        position_value = sum(p.market_value for p in self.positions.values())
        return self.cash + position_value

    @property
    def position_count(self) -> int:
        return len(self.positions)

    def update_prices(self, prices: dict[str, float]) -> None:
        """Update current prices for all positions."""
        for symbol, position in self.positions.items():
            if symbol in prices:
                position.current_price = prices[symbol]

    def get_weights(self) -> dict[str, float]:
        """Get current position weights."""
        equity = self.equity
        if equity == 0:
            return {}
        return {
            symbol: pos.market_value / equity for symbol, pos in self.positions.items()
        }


@dataclass
class TransactionCosts:
    """Transaction cost model."""

    commission_per_share: float = 0.0
    commission_min: float = 0.0
    commission_max: float = 0.0
    slippage_bps: float = 10.0  # Basis points

    def calculate(self, shares: float, price: float) -> tuple[float, float]:
        """Calculate commission and slippage for a trade.

        Returns:
            Tuple of (commission, slippage)
        """
        # Commission
        commission = shares * self.commission_per_share
        if self.commission_min > 0:
            commission = max(commission, self.commission_min)
        if self.commission_max > 0:
            commission = min(commission, self.commission_max)

        # Slippage
        slippage = shares * price * (self.slippage_bps / 10000)

        return commission, slippage


class PortfolioManager:
    """Manages portfolio operations with transaction cost modeling."""

    def __init__(
        self,
        initial_capital: float,
        transaction_costs: TransactionCosts | None = None,
    ) -> None:
        """Initialize portfolio manager.

        Args:
            initial_capital: Starting cash
            transaction_costs: Cost model for trades
        """
        self.portfolio = Portfolio(cash=initial_capital)
        self.costs = transaction_costs or TransactionCosts()
        self.initial_capital = initial_capital

    def buy(
        self,
        symbol: str,
        shares: float,
        price: float,
        trade_date: date,
    ) -> Trade | None:
        """Execute a buy order.

        Args:
            symbol: Ticker symbol
            shares: Number of shares
            price: Execution price
            trade_date: Trade date

        Returns:
            Trade object if successful, None if insufficient cash
        """
        commission, slippage = self.costs.calculate(shares, price)
        total_cost = shares * price + commission + slippage

        if total_cost > self.portfolio.cash:
            return None

        trade = Trade(
            symbol=symbol,
            date=trade_date,
            side="buy",
            shares=shares,
            price=price,
            commission=commission,
            slippage=slippage,
        )

        # Update portfolio
        self.portfolio.cash -= total_cost

        if symbol in self.portfolio.positions:
            # Add to existing position (average in)
            pos = self.portfolio.positions[symbol]
            total_shares = pos.shares + shares
            avg_price = (pos.cost_basis + shares * price) / total_shares
            pos.shares = total_shares
            pos.entry_price = avg_price
        else:
            # New position
            self.portfolio.positions[symbol] = Position(
                symbol=symbol,
                shares=shares,
                entry_price=price,
                entry_date=trade_date,
                current_price=price,
            )

        self.portfolio.trade_history.append(trade)
        return trade

    def sell(
        self,
        symbol: str,
        shares: float,
        price: float,
        trade_date: date,
    ) -> Trade | None:
        """Execute a sell order.

        Args:
            symbol: Ticker symbol
            shares: Number of shares
            price: Execution price
            trade_date: Trade date

        Returns:
            Trade object if successful, None if insufficient shares
        """
        if symbol not in self.portfolio.positions:
            return None

        position = self.portfolio.positions[symbol]
        if shares > position.shares:
            return None

        commission, slippage = self.costs.calculate(shares, price)
        net_proceeds = shares * price - commission - slippage

        trade = Trade(
            symbol=symbol,
            date=trade_date,
            side="sell",
            shares=shares,
            price=price,
            commission=commission,
            slippage=slippage,
        )

        # Update portfolio
        self.portfolio.cash += net_proceeds
        position.shares -= shares

        if position.shares <= 0:
            del self.portfolio.positions[symbol]

        self.portfolio.trade_history.append(trade)
        return trade

    def close_position(
        self,
        symbol: str,
        price: float,
        trade_date: date,
    ) -> Trade | None:
        """Close an entire position.

        Args:
            symbol: Ticker symbol
            price: Execution price
            trade_date: Trade date

        Returns:
            Trade object if successful
        """
        if symbol not in self.portfolio.positions:
            return None

        shares = self.portfolio.positions[symbol].shares
        return self.sell(symbol, shares, price, trade_date)

    def rebalance_to_targets(
        self,
        target_weights: dict[str, float],
        prices: dict[str, float],
        trade_date: date,
    ) -> list[Trade]:
        """Rebalance portfolio to target weights.

        Args:
            target_weights: Target weight for each symbol
            prices: Current prices
            trade_date: Trade date

        Returns:
            List of executed trades
        """
        trades = []

        # Update current prices
        self.portfolio.update_prices(prices)
        current_equity = self.portfolio.equity

        # Calculate target values
        target_values = {
            symbol: weight * current_equity for symbol, weight in target_weights.items()
        }

        # Current values
        current_values = {
            symbol: pos.market_value for symbol, pos in self.portfolio.positions.items()
        }

        # First, handle sells
        for symbol in list(self.portfolio.positions.keys()):
            target = target_values.get(symbol, 0.0)
            current = current_values.get(symbol, 0.0)

            if target < current and symbol in prices:
                # Reduce position
                value_diff = current - target
                shares_to_sell = value_diff / prices[symbol]
                trade = self.sell(symbol, shares_to_sell, prices[symbol], trade_date)
                if trade:
                    trades.append(trade)

        # Then, handle buys
        for symbol, target in target_values.items():
            if symbol not in prices:
                continue

            current = current_values.get(symbol, 0.0)

            if target > current:
                # Increase position
                value_diff = target - current
                shares_to_buy = value_diff / prices[symbol]
                trade = self.buy(symbol, shares_to_buy, prices[symbol], trade_date)
                if trade:
                    trades.append(trade)

        return trades

    def get_returns_series(self) -> pd.Series:
        """Calculate daily returns from trade history.

        Note: Requires equity snapshots to be tracked separately.
        """
        # This is a simplified version - full implementation would
        # track daily equity values
        return pd.Series(dtype=float)
