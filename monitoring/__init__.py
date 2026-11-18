"""Monitoring module for NetPulse AI: telemetry collection, threshold rules, and trend tracking."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .collector import Collector
    from .monitor import NetworkMonitor
    from .rules import Breach, ThresholdConfig, evaluate_measurement, get_target_tier
    from .trends import RollingTrendTracker


def __getattr__(name: str):
    if name == "Collector":
        from .collector import Collector

        return Collector
    if name == "NetworkMonitor":
        from .monitor import NetworkMonitor

        return NetworkMonitor
    if name in ("ThresholdConfig", "Breach", "evaluate_measurement", "get_target_tier"):
        from . import rules

        return getattr(rules, name)
    if name == "RollingTrendTracker":
        from .trends import RollingTrendTracker

        return RollingTrendTracker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "Collector",
    "NetworkMonitor",
    "ThresholdConfig",
    "Breach",
    "RollingTrendTracker",
    "evaluate_measurement",
    "get_target_tier",
]
