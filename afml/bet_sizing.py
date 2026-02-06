"""
Kelly Criterion Bet Sizing (AFML Chapter 10)

How much to bet? Kelly criterion maximizes long-run geometric growth rate.
Full Kelly is theoretically optimal but volatile; half-Kelly is the
practical standard for position sizing.

DO NOT use fixed position sizes. Use Kelly-derived fractions.
"""

from dataclasses import dataclass

import numpy as np


@dataclass
class KellyResult:
    """
    Result of Kelly criterion calculation.

    Attributes
    ----------
    full_kelly : float
        Optimal bet fraction f* = (p*b - q) / b
    half_kelly : float
        f*/2 (standard safety margin)
    probability : float
        Win probability (p)
    odds : float
        Win/loss ratio (b)
    expected_value : float
        Edge per bet: p*b - q
    """

    full_kelly: float
    half_kelly: float
    probability: float
    odds: float
    expected_value: float


def kelly_criterion(prob_win: float, odds: float = 1.0) -> KellyResult:
    """
    Compute Kelly criterion optimal bet fraction.

    f* = (p*b - q) / b where q = 1 - p

    Parameters
    ----------
    prob_win : float
        Probability of winning (0 to 1)
    odds : float
        Win/loss ratio: amount won per unit risked (default 1.0 = even odds)

    Returns
    -------
    KellyResult
        Kelly fractions and supporting statistics

    Example
    -------
    >>> result = kelly_criterion(0.6, 1.0)
    >>> print(f"Bet {result.half_kelly:.1%} of capital")
    """
    # Clamp probability to valid range
    prob_win = float(np.clip(prob_win, 0.0, 1.0))

    if odds <= 0:
        raise ValueError(f"Odds must be positive, got {odds}")

    prob_lose = 1.0 - prob_win
    expected_value = prob_win * odds - prob_lose

    # f* = (p*b - q) / b
    full_kelly = expected_value / odds if odds > 0 else 0.0
    half_kelly = full_kelly / 2.0

    return KellyResult(
        full_kelly=full_kelly,
        half_kelly=half_kelly,
        probability=prob_win,
        odds=odds,
        expected_value=expected_value,
    )


def discrete_kelly(
    prob_win: float,
    odds: float,
    step: float = 0.05,
) -> float:
    """
    Kelly fraction rounded to discrete step size.

    Practical for position sizing where you can't allocate
    arbitrary fractions (e.g., must be multiples of 5%).

    Parameters
    ----------
    prob_win : float
        Probability of winning
    odds : float
        Win/loss ratio
    step : float
        Step size to round to (default 0.05 = 5%)

    Returns
    -------
    float
        Kelly fraction rounded down to nearest step (never negative)

    Example
    -------
    >>> discrete_kelly(0.55, 1.0, step=0.05)
    0.05
    """
    result = kelly_criterion(prob_win, odds)
    if result.full_kelly <= 0:
        return 0.0
    # Round down to nearest step (use round to avoid floating point drift)
    return float(round(np.floor(result.full_kelly / step + 1e-10) * step, 10))
