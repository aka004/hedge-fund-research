"""
Stationarity Checks (AFML Chapter 5)

Most ML models assume stationary data (statistical properties don't change
over time). Financial time series like prices are non-stationary. Using raw
prices in models produces spurious correlations.

This module provides stationarity diagnostics and warnings.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class AdfResult:
    """
    Result of Augmented Dickey-Fuller test.

    Attributes
    ----------
    statistic : float
        ADF test statistic
    p_value : float
        P-value for the test
    is_stationary : bool
        True if p_value < significance level
    critical_values : dict
        Critical values at 1%, 5%, 10%
    n_lags : int
        Number of lags used
    recommendation : str
        Plain-English recommendation
    """

    statistic: float
    p_value: float
    is_stationary: bool
    critical_values: dict
    n_lags: int
    recommendation: str


def adf_test(
    series: pd.Series,
    max_lags: int | None = None,
    significance: float = 0.05,
) -> AdfResult:
    """
    Augmented Dickey-Fuller test for stationarity.

    H0: Series has a unit root (non-stationary)
    H1: Series is stationary

    Parameters
    ----------
    series : pd.Series
        Time series to test
    max_lags : int, optional
        Maximum lags to include. If None, uses 12*(n/100)^(1/4)
    significance : float
        Significance level (default 0.05)

    Returns
    -------
    AdfResult
        Test results and recommendation

    Example
    -------
    >>> result = adf_test(prices)
    >>> if not result.is_stationary:
    ...     print(result.recommendation)
    """
    from statsmodels.tsa.stattools import adfuller

    series = series.dropna()

    if max_lags is None:
        max_lags = int(12 * (len(series) / 100) ** 0.25)

    result = adfuller(series, maxlag=max_lags, autolag="AIC")

    statistic = result[0]
    p_value = result[1]
    n_lags = result[2]
    critical_values = result[4]

    is_stationary = p_value < significance

    if is_stationary:
        recommendation = "Series is stationary. Safe to use in models."
    else:
        recommendation = (
            f"WARNING: Series is non-stationary (p={p_value:.4f}). "
            "Consider differencing or fractional differentiation (V2)."
        )

    return AdfResult(
        statistic=statistic,
        p_value=p_value,
        is_stationary=is_stationary,
        critical_values=critical_values,
        n_lags=n_lags,
        recommendation=recommendation,
    )


def stationarity_check(
    data: pd.DataFrame,
    significance: float = 0.05,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Check stationarity of all columns in a DataFrame.

    Parameters
    ----------
    data : pd.DataFrame
        Features to check (each column tested separately)
    significance : float
        Significance level (default 0.05)

    Returns
    -------
    results_df : pd.DataFrame
        Test results for each column
    warnings : List[str]
        List of warning messages for non-stationary features

    Example
    -------
    >>> results, warnings = stationarity_check(features_df)
    >>> if warnings:
    ...     print("Non-stationary features detected:")
    ...     for w in warnings:
    ...         print(f"  - {w}")
    """
    results = []
    warnings = []

    for col in data.columns:
        try:
            result = adf_test(data[col], significance=significance)
            results.append(
                {
                    "feature": col,
                    "statistic": result.statistic,
                    "p_value": result.p_value,
                    "is_stationary": result.is_stationary,
                    "n_lags": result.n_lags,
                }
            )

            if not result.is_stationary:
                warnings.append(f"{col}: p-value={result.p_value:.4f}")

        except Exception as e:
            results.append(
                {
                    "feature": col,
                    "statistic": np.nan,
                    "p_value": np.nan,
                    "is_stationary": False,
                    "n_lags": 0,
                }
            )
            warnings.append(f"{col}: Error - {str(e)}")

    results_df = pd.DataFrame(results)

    return results_df, warnings


@dataclass
class RollingStationarityResult:
    """Result of rolling stationarity diagnostic (STATN).

    Attributes
    ----------
    rolling_pvalues : pd.Series
        ADF p-value for each rolling window (index = window end position)
    fraction_stationary : float
        Fraction of windows passing ADF test (p < significance)
    passes : bool
        True if fraction_stationary >= threshold (e.g. 0.80)
    recommendation : str
        Plain-English interpretation
    """

    rolling_pvalues: pd.Series
    fraction_stationary: float
    passes: bool
    recommendation: str


def rolling_statn(
    excess_returns: pd.Series,
    window: int = 60,
    significance: float = 0.05,
    threshold_fraction: float = 0.80,
) -> RollingStationarityResult:
    """Rolling stationarity diagnostic (Masters STATN).

    Runs ADF test on each rolling window of `window` observations.
    Measures what fraction of windows are stationary.

    Parameters
    ----------
    excess_returns : pd.Series
        Series of excess returns (strategy return minus benchmark)
    window : int
        Rolling window size in observations (default 60)
    significance : float
        ADF significance level (default 0.05)
    threshold_fraction : float
        Minimum fraction of stationary windows to pass (default 0.80)

    Returns
    -------
    RollingStationarityResult

    Notes
    -----
    Calls existing adf_test() internally — no ADF logic duplication.
    Requires at least window+1 observations.
    """
    if len(excess_returns) < window + 1:
        raise ValueError(
            f"Need at least {window + 1} observations, got {len(excess_returns)}"
        )

    pvalues = {}
    for i in range(window, len(excess_returns)):
        window_slice = excess_returns.iloc[i - window + 1 : i + 1]
        result = adf_test(window_slice, significance=significance)
        pvalues[i] = result.p_value

    rolling_pvalues = pd.Series(pvalues)
    fraction_stationary = float((rolling_pvalues < significance).mean())
    passes = fraction_stationary >= threshold_fraction

    if passes:
        recommendation = (
            f"Series is stationary in {fraction_stationary:.1%} of rolling windows "
            f"(>= {threshold_fraction:.1%} threshold). Safe to use."
        )
    else:
        recommendation = (
            f"WARNING: Series is stationary in only {fraction_stationary:.1%} of "
            f"rolling windows (< {threshold_fraction:.1%} threshold). "
            "Non-stationarity detected — consider differencing."
        )

    return RollingStationarityResult(
        rolling_pvalues=rolling_pvalues,
        fraction_stationary=fraction_stationary,
        passes=passes,
        recommendation=recommendation,
    )


def transform_to_stationary(
    series: pd.Series,
    method: str = "diff",
) -> pd.Series:
    """
    Transform a non-stationary series to stationary.

    Parameters
    ----------
    series : pd.Series
        Original series
    method : str
        Transformation method:
        - 'diff': First difference (returns)
        - 'log_diff': Log returns
        - 'pct_change': Percentage change

    Returns
    -------
    pd.Series
        Transformed series

    Note
    ----
    For fractional differentiation (preserves more memory), see V2 features.
    """
    if method == "diff":
        return series.diff().dropna()
    elif method == "log_diff":
        return np.log(series).diff().dropna()
    elif method == "pct_change":
        return series.pct_change().dropna()
    else:
        raise ValueError(f"Unknown method: {method}")
