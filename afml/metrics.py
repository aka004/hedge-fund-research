"""
Deflated Sharpe Ratio / PSR (AFML Chapter 14)

Raw Sharpe ratios are misleading because they ignore:
- Non-normal returns (skewness, fat tails)
- Selection bias (you tested N strategies, picked the best)
- Short track records

PSR gives the probability that true Sharpe exceeds benchmark.

DO NOT use raw Sharpe ratio for strategy validation.
"""

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass
class SharpeResult:
    """
    Result of Sharpe ratio calculation with adjustments.

    Attributes
    ----------
    sharpe : float
        Raw Sharpe ratio
    psr : float
        Probabilistic Sharpe Ratio (0-1)
    psr_confidence : float
        Confidence level (psr as percentage)
    passes_threshold : bool
        Whether PSR >= threshold (default 0.95)
    n_observations : int
        Number of return observations
    skewness : float
        Skewness of returns
    kurtosis : float
        Excess kurtosis of returns
    """

    sharpe: float
    psr: float
    psr_confidence: float
    passes_threshold: bool
    n_observations: int
    skewness: float
    kurtosis: float


def sharpe_standard_error(
    sharpe: float,
    n: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """
    Compute standard error of Sharpe ratio estimate.

    Adjusts for non-normality using Lo (2002) and Mertens (2002).

    Parameters
    ----------
    sharpe : float
        Observed Sharpe ratio
    n : int
        Number of observations
    skewness : float
        Skewness of returns (default 0 = normal)
    kurtosis : float
        Kurtosis of returns (default 3 = normal)

    Returns
    -------
    float
        Standard error of Sharpe estimate
    """
    # Excess kurtosis
    excess_kurt = kurtosis - 3

    # Mertens (2002) formula for SE(SR) under non-normality
    se_sq = (
        1 + 0.5 * sharpe**2 - skewness * sharpe + (excess_kurt / 4) * sharpe**2
    ) / n

    return np.sqrt(max(se_sq, 1e-10))


def deflated_sharpe(
    returns: np.ndarray,
    benchmark_sharpe: float = 0.0,
    n_strategies_tested: int = 1,
    annualization: float = 252,
    threshold: float = 0.95,
) -> SharpeResult:
    """
    Compute Probabilistic Sharpe Ratio (PSR).

    PSR = P(true SR > benchmark | observed data)

    Parameters
    ----------
    returns : np.ndarray
        Array of returns (daily)
    benchmark_sharpe : float
        Benchmark Sharpe to beat (default 0)
    n_strategies_tested : int
        Number of strategies tested (for multiple testing adjustment)
    annualization : float
        Trading days per year (default 252)
    threshold : float
        PSR threshold to pass (default 0.95 = 95% confidence)

    Returns
    -------
    SharpeResult
        Complete Sharpe analysis including PSR

    Example
    -------
    >>> result = deflated_sharpe(strategy_returns, n_strategies_tested=10)
    >>> if result.passes_threshold:
    ...     print("Strategy approved")
    >>> else:
    ...     print(f"PSR too low: {result.psr_confidence:.1f}%")
    """
    returns = np.asarray(returns)
    returns = returns[~np.isnan(returns)]

    n = len(returns)
    if n < 5:
        raise ValueError(f"Need at least 5 observations, got {n}")

    # Compute moments
    mean_ret = np.mean(returns)
    std_ret = np.std(returns, ddof=1)
    skewness = stats.skew(returns)
    kurtosis = stats.kurtosis(returns, fisher=False)  # Regular kurtosis

    # Raw Sharpe (annualized)
    sharpe = (mean_ret / std_ret) * np.sqrt(annualization) if std_ret > 0 else 0

    # Adjust benchmark for multiple testing (Bailey & López de Prado)
    if n_strategies_tested > 1:
        # Expected maximum Sharpe from N random strategies
        expected_max_sharpe = (1 - np.euler_gamma) * stats.norm.ppf(
            1 - 1 / n_strategies_tested
        ) + np.euler_gamma * stats.norm.ppf(1 - 1 / (n_strategies_tested * np.e))
        benchmark_sharpe = max(benchmark_sharpe, expected_max_sharpe)

    # Standard error of Sharpe
    se = sharpe_standard_error(sharpe, n, skewness, kurtosis)

    # PSR = Φ[(SR - SR*) / SE(SR)]
    z_score = (sharpe - benchmark_sharpe) / se if se > 0 else 0
    psr = stats.norm.cdf(z_score)

    return SharpeResult(
        sharpe=sharpe,
        psr=psr,
        psr_confidence=psr * 100,
        passes_threshold=psr >= threshold,
        n_observations=n,
        skewness=skewness,
        kurtosis=kurtosis,
    )


# Alias
psr = deflated_sharpe
