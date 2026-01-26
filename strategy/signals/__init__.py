"""Signal generators for trading strategies."""

from strategy.signals.base import Signal, SignalGenerator
from strategy.signals.combiner import SignalCombiner, SignalWeight
from strategy.signals.momentum import MomentumSignal
from strategy.signals.social import SocialSignal
from strategy.signals.value import ValueSignal

__all__ = [
    "Signal",
    "SignalGenerator",
    "MomentumSignal",
    "ValueSignal",
    "SocialSignal",
    "SignalCombiner",
    "SignalWeight",
]

# Optional signals - only available if dependencies are installed
try:
    from strategy.signals.politician import PoliticianSignal

    __all__.append("PoliticianSignal")
except ImportError:
    PoliticianSignal = None  # type: ignore[misc, assignment]
