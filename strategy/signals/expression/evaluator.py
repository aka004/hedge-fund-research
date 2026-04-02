"""
AST evaluator — walks the parse tree and evaluates against OHLCV DataFrames.

Each node evaluates to either a pd.DataFrame (dates × symbols) or a scalar float.
The final result is the last row (as_of_date), giving one score per symbol.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from strategy.signals.expression.operators import OPERATOR_REGISTRY
from strategy.signals.expression.parser import (
    BinOpNode,
    ColumnNode,
    FuncCallNode,
    Node,
    NumberNode,
    UnaryNegNode,
    parse,
)


def evaluate(node: Node, ohlcv: dict[str, pd.DataFrame]) -> pd.DataFrame | float:
    """Recursively evaluate an AST node against OHLCV data.

    Args:
        node: AST node from the parser.
        ohlcv: Dict mapping column names to DataFrames (dates × symbols).
               Must include "close", "open", "high", "low", "volume".

    Returns:
        DataFrame (dates × symbols) or scalar float.
    """
    if isinstance(node, NumberNode):
        return node.value

    if isinstance(node, ColumnNode):
        name = node.name
        if name == "returns":
            close = ohlcv["close"]
            return np.log(close / close.shift(1))
        if name not in ohlcv:
            raise ValueError(f"Column {name!r} not in OHLCV data")
        return ohlcv[name]

    if isinstance(node, UnaryNegNode):
        child = evaluate(node.child, ohlcv)
        return -child

    if isinstance(node, BinOpNode):
        left = evaluate(node.left, ohlcv)
        right = evaluate(node.right, ohlcv)
        if node.op == "+":
            return left + right
        if node.op == "-":
            return left - right
        if node.op == "*":
            return left * right
        if node.op == "/":
            # NaN-safe division
            if isinstance(right, (int, float)):
                return left / right if right != 0 else left * np.nan
            return left / right.replace(0, np.nan)
        raise ValueError(f"Unknown operator: {node.op!r}")

    if isinstance(node, FuncCallNode):
        spec = OPERATOR_REGISTRY[node.name]
        # Evaluate expression arguments (all but the last if has_window)
        n_expr = spec.n_expr_args
        expr_args = [evaluate(arg, ohlcv) for arg in node.args[:n_expr]]
        if spec.has_window:
            window = int(node.args[-1].value)  # already validated as NumberNode
            return spec.func(*expr_args, window)
        return spec.func(*expr_args)

    raise TypeError(f"Unknown AST node type: {type(node).__name__}")


def evaluate_expression(
    expression: str,
    ohlcv: dict[str, pd.DataFrame],
    as_of_date: date,
) -> pd.Series:
    """Parse, evaluate, and return per-symbol scores for a single date.

    Truncates all OHLCV data to <= as_of_date before evaluation (no look-ahead).
    Returns the last row of the result as a pd.Series (symbol → score).
    """
    # Truncate to prevent look-ahead
    as_of_ts = pd.Timestamp(as_of_date)
    truncated = {
        col: df.loc[:as_of_ts]
        for col, df in ohlcv.items()
    }

    # Check we have data
    ref = truncated.get("close")
    if ref is None or ref.empty:
        return pd.Series(dtype=float)

    # Parse and evaluate
    ast = parse(expression)
    result = evaluate(ast, truncated)

    # Handle scalar result (broadcast to all symbols)
    if isinstance(result, (int, float)):
        return pd.Series(result, index=ref.columns)

    # Extract last row
    if result.empty:
        return pd.Series(dtype=float)
    return result.iloc[-1]
