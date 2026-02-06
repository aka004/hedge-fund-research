"""
Mock data for deferred features (AlphaGPT discovered factors).
"""

from app.models.dashboard_schemas import DiscoveredFactor, FactorsResponse


def get_mock_factors() -> FactorsResponse:
    """Return mock discovered factors (AlphaGPT deferred)."""
    factors = [
        DiscoveredFactor(
            id=1,
            formula="(fracdiff x vol_accel) + sentiment",
            psr=0.94,
            sharpe=1.82,
            max_dd=-8.2,
            trades=47,
            status="active",
            is_mock=True,
        ),
        DiscoveredFactor(
            id=2,
            formula="momentum - (deviation x volatility)",
            psr=0.91,
            sharpe=1.64,
            max_dd=-11.4,
            trades=52,
            status="active",
            is_mock=True,
        ),
        DiscoveredFactor(
            id=3,
            formula="(pressure + sentiment) x fracdiff",
            psr=0.88,
            sharpe=1.51,
            max_dd=-9.7,
            trades=38,
            status="active",
            is_mock=True,
        ),
        DiscoveredFactor(
            id=4,
            formula="earnings_surprise + (momentum x volume)",
            psr=0.85,
            sharpe=1.43,
            max_dd=-12.1,
            trades=61,
            status="monitoring",
            is_mock=True,
        ),
        DiscoveredFactor(
            id=5,
            formula="kyle_lambda - volatility",
            psr=0.79,
            sharpe=1.21,
            max_dd=-14.5,
            trades=33,
            status="monitoring",
            is_mock=True,
        ),
        DiscoveredFactor(
            id=6,
            formula="(volume / deviation) + momentum",
            psr=0.72,
            sharpe=0.98,
            max_dd=-18.3,
            trades=44,
            status="rejected",
            is_mock=True,
        ),
        DiscoveredFactor(
            id=7,
            formula="fracdiff x (sentiment - pressure)",
            psr=0.68,
            sharpe=0.87,
            max_dd=-16.8,
            trades=29,
            status="rejected",
            is_mock=True,
        ),
    ]
    return FactorsResponse(factors=factors, is_mock=True)
