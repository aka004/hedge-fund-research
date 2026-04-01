"""Macro indicator configuration -- series IDs, thresholds, display metadata."""

INDICATOR_GROUPS = {
    "fed_policy": {
        "label": "FED POLICY",
        "color": "#ff8c00",
        "indicators": [
            {
                "id": "fed_funds",
                "name": "Fed Funds Rate",
                "source": "fred",
                "series_id": "DFF",
                "unit": "percent",
                "display_format": "range",
                "hawk_level": 4.5,
                "dove_level": 2.5,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [
                    {"label": "Neutral Rate", "value": 2.5, "color": "#ff8c00"}
                ],
            },
            {
                "id": "net_reserves",
                "name": "Net Reserves",
                "source": "fred_computed",
                "series_ids": ["WRESBAL", "RRPONTSYD"],
                "computation": "subtract",
                "unit_note": "WRESBAL in millions, RRPONTSYD in billions — normalize in service",
                "unit": "millions",
                "display_format": "currency_T",
                "hawk_level": 1_000_000,  # below $1T (in millions) = hawk
                "dove_level": 2_000_000,  # above $2T (in millions) = dove
                "trend_weight": 0.4,
                "invert_trend": True,
                "reference_lines": [
                    {"label": "Pre-COVID Level", "value": 1_500_000, "color": "#888"}
                ],
            },
            {
                "id": "deficit",
                "name": "Deficit (CBO est)",
                "source": "fred",
                "series_id": "FYFSD",
                "unit": "millions",
                "display_format": "currency_T",
                "hawk_level": -1_500_000,  # deficit > $1.5T (negative, in millions)
                "dove_level": -500_000,  # deficit < $500B
                "trend_weight": 0.3,
                "invert_trend": True,  # more negative = more hawkish
                "reference_lines": [],
            },
        ],
    },
    "inflation": {
        "label": "INFLATION",
        "color": "#ff3b30",
        "indicators": [
            {
                "id": "cpi",
                "name": "CPI YoY",
                "source": "fred",
                "series_id": "CPIAUCSL",
                "unit": "percent_yoy",
                "display_format": "percent",
                "hawk_level": 3.0,
                "dove_level": 2.0,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [
                    {"label": "Fed Target", "value": 2.0, "color": "#ff8c00"}
                ],
            },
            {
                "id": "core_cpi",
                "name": "Core CPI YoY",
                "source": "fred",
                "series_id": "CPILFESL",
                "unit": "percent_yoy",
                "display_format": "percent",
                "hawk_level": 3.0,
                "dove_level": 2.0,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [
                    {"label": "Fed Target", "value": 2.0, "color": "#ff8c00"}
                ],
            },
            {
                "id": "ppi",
                "name": "PPI YoY",
                "source": "fred",
                "series_id": "PPIACO",
                "unit": "percent_yoy",
                "display_format": "percent",
                "hawk_level": 3.0,
                "dove_level": 1.0,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [],
            },
            {
                "id": "core_ppi",
                "name": "Core PPI YoY",
                "source": "fred",
                "series_id": "WPSFD4131",
                "unit": "percent_yoy",
                "display_format": "percent",
                "hawk_level": 3.0,
                "dove_level": 1.0,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [],
            },
            {
                "id": "pce",
                "name": "PCE YoY",
                "source": "fred",
                "series_id": "PCEPI",
                "unit": "percent_yoy",
                "display_format": "percent",
                "hawk_level": 2.5,
                "dove_level": 1.5,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [
                    {"label": "Fed Target", "value": 2.0, "color": "#ff8c00"}
                ],
            },
            {
                "id": "core_pce",
                "name": "Core PCE YoY",
                "source": "fred",
                "series_id": "PCEPILFE",
                "unit": "percent_yoy",
                "display_format": "percent",
                "hawk_level": 2.5,
                "dove_level": 1.5,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [
                    {"label": "Fed Target", "value": 2.0, "color": "#ff8c00"}
                ],
            },
        ],
    },
    "employment": {
        "label": "EMPLOYMENT",
        "color": "#0a84ff",
        "indicators": [
            {
                "id": "unemployment",
                "name": "Unemployment Rate",
                "source": "fred",
                "series_id": "UNRATE",
                "unit": "percent",
                "display_format": "percent",
                "hawk_level": 3.5,
                "dove_level": 4.5,
                "trend_weight": 0.3,
                "invert_trend": True,
                "reference_lines": [
                    {"label": "NAIRU", "value": 4.0, "color": "#0a84ff"}
                ],
            },
            {
                "id": "nfp",
                "name": "Nonfarm Payrolls",
                "source": "fred",
                "series_id": "PAYEMS",
                "unit": "mom_change_thousands",
                "display_format": "change_K",
                "hawk_level": 250,
                "dove_level": 100,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [],
            },
        ],
    },
    "markets": {
        "label": "MARKETS & COMMODITIES",
        "color": "#00d26a",
        "indicators": [
            {
                "id": "sp500",
                "name": "S&P 500",
                "source": "yahoo",
                "ticker": "^GSPC",
                "unit": "price",
                "display_format": "number",
                "signal_type": "ma200",
                "trend_weight": 0.0,
                "invert_trend": False,
                "reference_lines": [
                    {
                        "label": "200-Day MA",
                        "value": None,
                        "color": "#ff8c00",
                        "dynamic": True,
                    }
                ],
            },
            {
                "id": "brent",
                "name": "Brent Crude",
                "source": "yahoo",
                "ticker": "BZ=F",
                "unit": "price",
                "display_format": "currency",
                "hawk_level": 90,
                "dove_level": 60,
                "trend_weight": 0.3,
                "invert_trend": False,
                "reference_lines": [],
            },
            {
                "id": "vix",
                "name": "VIX",
                "source": "yahoo",
                "ticker": "^VIX",
                "unit": "index",
                "display_format": "number",
                "hawk_level": 15,
                "dove_level": 25,
                "trend_weight": 0.2,
                "invert_trend": True,
                "reference_lines": [
                    {"label": "Long-term Avg", "value": 20, "color": "#888"}
                ],
            },
            {
                "id": "sentiment",
                "name": "Sentiment (AAII)",
                "source": "fred",
                "series_id": "AAII",
                "unit": "percent",
                "display_format": "number",
                "hawk_level": 45,
                "dove_level": 25,
                "trend_weight": 0.2,
                "invert_trend": False,
                "fallback": "vix",
                "reference_lines": [],
            },
        ],
    },
}


def get_all_indicators():
    """Flatten all indicators into a list."""
    indicators = []
    for group_key, group in INDICATOR_GROUPS.items():
        for ind in group["indicators"]:
            indicators.append(
                {**ind, "group": group_key, "group_label": group["label"]}
            )
    return indicators


def get_indicator_by_id(indicator_id: str):
    """Find an indicator config by its ID."""
    for group in INDICATOR_GROUPS.values():
        for ind in group["indicators"]:
            if ind["id"] == indicator_id:
                return ind
    return None
