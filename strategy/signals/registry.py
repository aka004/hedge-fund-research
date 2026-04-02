"""
Signal registry — maps factor type names to generator classes and parameter schemas.

AlphaGPT uses this to know what factors exist and what parameters are valid.
Adding a new factor type here makes it immediately available to the LLM.
"""

from dataclasses import dataclass
from typing import Any

# ── Parameter schema types ────────────────────────────────────────────────────

@dataclass
class ParamSchema:
    type: str           # "int" | "float" | "bool" | "choice"
    default: Any
    choices: list | None = None   # for "choice" type
    min: float | None = None      # for int/float
    max: float | None = None      # for int/float
    description: str = ""


# ── Registry entry ────────────────────────────────────────────────────────────

@dataclass
class FactorEntry:
    name: str
    cls_path: str          # importable path, e.g. "strategy.signals.momentum.MomentumSignal"
    requires: list[str]    # constructor dependency names: "duckdb_store" | "parquet_storage"
    params: dict[str, ParamSchema]
    description: str
    data_coverage: str     # "always" | "if_cached" | "rarely"


# ── Factor space ──────────────────────────────────────────────────────────────

FACTOR_REGISTRY: dict[str, FactorEntry] = {

    "momentum": FactorEntry(
        name="momentum",
        cls_path="strategy.signals.momentum.MomentumSignal",
        requires=["duckdb_store"],
        params={
            "lookback_months": ParamSchema(
                type="int", default=12, min=3, max=24,
                description="Return lookback window in months (classic: 12)"
            ),
            "skip_months": ParamSchema(
                type="int", default=1, min=0, max=3,
                description="Recent months to skip to avoid short-term reversal (classic: 1)"
            ),
            "ma_window_days": ParamSchema(
                type="int", default=200, min=50, max=300,
                description="MA trend filter window. 0 = disable MA filter entirely"
            ),
        },
        description=(
            "12-1 month price momentum. Buys recent winners above their MA. "
            "Best documented equity factor (Jegadeesh & Titman 1993). "
            "Fails in sharp reversals (2009, 2020 March). "
            "Try: longer lookback for less turnover, skip=0 for short-term momentum."
        ),
        data_coverage="always",
    ),

    "value": FactorEntry(
        name="value",
        cls_path="strategy.signals.value.ValueSignal",
        requires=["parquet_storage"],
        params={
            "max_pe": ParamSchema(
                type="float", default=50.0, min=10.0, max=100.0,
                description="Maximum P/E ratio. Lower = value tilt. 999 = no PE filter."
            ),
            "require_positive_earnings": ParamSchema(
                type="bool", default=True,
                description="Reject stocks with negative TTM earnings"
            ),
            "require_revenue_growth": ParamSchema(
                type="bool", default=True,
                description="Reject stocks with negative YoY revenue growth"
            ),
        },
        description=(
            "Fundamental value filter. Score = 1/PE (cheaper = higher score). "
            "Combines well with momentum (value×momentum reduces momentum crashes). "
            "Note: fundamentals data may be missing for many tickers — "
            "symbols with no data are silently skipped. Best as a secondary filter."
        ),
        data_coverage="if_cached",
    ),

    "social": FactorEntry(
        name="social",
        cls_path="strategy.signals.social.SocialSignal",
        requires=["parquet_storage"],
        params={
            "min_message_count": ParamSchema(
                type="int", default=5, min=1, max=50,
                description="Minimum StockTwits messages to consider signal valid"
            ),
            "lookback_hours": ParamSchema(
                type="int", default=24, min=4, max=72,
                description="Hours of sentiment data to aggregate"
            ),
        },
        description=(
            "StockTwits social sentiment. Score = bullish ratio. "
            "Contrarian at extremes (crowded longs reverse). "
            "Requires StockTwits data to be cached — may have gaps."
        ),
        data_coverage="if_cached",
    ),
}


# ── Backtest parameter space (what AlphaGPT can control beyond signals) ───────

BACKTEST_PARAM_SCHEMA: dict[str, ParamSchema] = {
    "profit_take_mult": ParamSchema(
        type="float", default=3.0, min=1.5, max=6.0,
        description="Profit target as multiple of 20d volatility (triple-barrier upper)"
    ),
    "stop_loss_mult": ParamSchema(
        type="float", default=1.5, min=0.5, max=3.0,
        description="Stop loss as multiple of 20d volatility (triple-barrier lower)"
    ),
    "max_holding_days": ParamSchema(
        type="int", default=30, min=10, max=60,
        description="Maximum holding period before forced exit (triple-barrier time)"
    ),
    "n_positions": ParamSchema(
        type="int", default=20, min=5, max=40,
        description="Max simultaneous positions. More = diversified but higher costs."
    ),
    "rebalance_frequency": ParamSchema(
        type="choice", default="monthly",
        choices=["weekly", "monthly"],
        description="How often to re-rank and rebalance. Weekly = more trades = more cost drag."
    ),
    "position_sizing": ParamSchema(
        type="choice", default="hrp",
        choices=["equal", "kelly", "hrp"],
        description="equal=1/N, kelly=signal×half-Kelly, hrp=HRP covariance weights"
    ),
    "use_cusum_gate": ParamSchema(
        type="bool", default=True,
        description="Only enter on CUSUM structural break events (filters noise entries)"
    ),
    "use_regime": ParamSchema(
        type="bool", default=True,
        description="Scale position sizes by macro+sentiment regime multiplier"
    ),
    "slippage_bps": ParamSchema(
        type="int", default=25, min=5, max=100,
        description="Round-trip slippage in basis points. 25 = realistic mid-cap."
    ),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_factor(name: str) -> FactorEntry:
    if name not in FACTOR_REGISTRY:
        raise ValueError(f"Unknown factor: '{name}'. Available: {list(FACTOR_REGISTRY)}")
    return FACTOR_REGISTRY[name]


def instantiate_signal(entry: FactorEntry, params: dict, duckdb_store, parquet_storage):
    """Dynamically instantiate a SignalGenerator from a registry entry + params."""
    import importlib
    module_path, class_name = entry.cls_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)

    # Build constructor kwargs
    kwargs = {}
    for dep in entry.requires:
        if dep == "duckdb_store":
            kwargs["duckdb_store"] = duckdb_store
        elif dep == "parquet_storage":
            kwargs[dep] = parquet_storage

    # Add user params (ignore unknown keys)
    valid_params = set(entry.params.keys())
    for k, v in params.items():
        if k in valid_params:
            kwargs[k] = v

    return cls(**kwargs)


def schema_as_text() -> str:
    """Return factor space as human-readable text for LLM prompt."""
    lines = []
    lines.append("=== AVAILABLE FACTORS ===")
    for name, entry in FACTOR_REGISTRY.items():
        coverage_note = {
            "always": "data always available",
            "if_cached": "data available if pre-fetched",
            "rarely": "data rarely available",
        }[entry.data_coverage]
        lines.append(f"\nFactor: {name}  [{coverage_note}]")
        lines.append(f"  {entry.description}")
        lines.append("  Parameters:")
        for pname, ps in entry.params.items():
            if ps.type == "choice":
                lines.append(f"    {pname}: {ps.choices} (default={ps.default}) — {ps.description}")
            elif ps.type == "bool":
                lines.append(f"    {pname}: bool (default={ps.default}) — {ps.description}")
            else:
                lines.append(f"    {pname}: {ps.type} [{ps.min}–{ps.max}] (default={ps.default}) — {ps.description}")

    lines.append("\n=== BACKTEST PARAMETERS ===")
    for pname, ps in BACKTEST_PARAM_SCHEMA.items():
        if ps.type == "choice":
            lines.append(f"  {pname}: {ps.choices} (default={ps.default}) — {ps.description}")
        elif ps.type == "bool":
            lines.append(f"  {pname}: bool (default={ps.default}) — {ps.description}")
        else:
            lines.append(f"  {pname}: {ps.type} [{ps.min}–{ps.max}] (default={ps.default}) — {ps.description}")

    return "\n".join(lines)
