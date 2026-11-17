"""Monitoring module for NetPulse AI: telemetry collection and polling."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .collector import Collector


def __getattr__(name: str):
    if name == "Collector":
        from .collector import Collector

        return Collector
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Collector"]

