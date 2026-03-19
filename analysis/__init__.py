"""Performance analysis and reporting."""

from analysis.metrics import (
    PerformanceMetrics,
    calculate_metrics,
    calculate_rolling_metrics,
    compare_to_benchmark,
)
from analysis.reports import (
    generate_summary_report,
    generate_summary_report_event,
    generate_trade_log,
    save_event_report,
    save_report_bundle,
)

__all__ = [
    "PerformanceMetrics",
    "calculate_metrics",
    "calculate_rolling_metrics",
    "compare_to_benchmark",
    "generate_summary_report",
    "generate_summary_report_event",
    "generate_trade_log",
    "save_event_report",
    "save_report_bundle",
]
