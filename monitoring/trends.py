"""Rolling trend calculation for network telemetry in NetPulse AI.

Maintains rolling windows of latency and packet-loss measurements per
target and computes rolling metrics, statistics, and directional trends.
"""

from collections import deque
from statistics import median
from typing import Any, Dict, List, Optional


class RollingTrendTracker:
    """Tracks rolling windows of measurements per target and computes statistical trends.

    Parameters:
        window_size: Maximum number of historical points per target in the rolling window.
                     Defaults to 20.
    """

    def __init__(self, window_size: int = 20) -> None:
        if isinstance(window_size, bool) or not isinstance(window_size, int):
            raise ValueError("window_size must be a positive integer")
        if window_size <= 0:
            raise ValueError("window_size must be a positive integer")
        self.window_size = window_size
        self._windows: Dict[str, deque] = {}

    def add_measurement(self, measurement: Dict[str, Any]) -> None:
        """Add a single measurement dict to the target's rolling window."""
        target_id = str(measurement["target_id"])
        if target_id not in self._windows:
            self._windows[target_id] = deque(maxlen=self.window_size)

        # Store copy of measurement
        self._windows[target_id].append(
            {
                "timestamp": str(measurement.get("timestamp", "")),
                "target_id": target_id,
                "target_type": str(measurement.get("target_type", "")),
                "latency_ms": measurement.get("latency_ms"),
                "loss_pct": measurement.get("loss_pct"),
                "status": str(measurement.get("status", "up")),
            }
        )

    def get_history(self, target_id: str) -> List[Dict[str, Any]]:
        """Return the current rolling window of measurements for a target in chronological order."""
        if target_id not in self._windows:
            return []
        return [dict(measurement) for measurement in self._windows[target_id]]

    def get_trend(self, target_id: str) -> Dict[str, Any]:
        """Compute rolling trend statistics for target.

        Returns:
            Dict containing:
              - count: number of samples in rolling window
              - current_latency_ms: latest sample latency
              - avg_latency_ms: rolling mean latency
              - min_latency_ms: rolling min latency
              - max_latency_ms: rolling max latency
              - latency_trend: 'rising' | 'falling' | 'stable'
              - current_loss_pct: latest sample loss
              - avg_loss_pct: rolling mean loss
              - min_loss_pct: rolling min loss
              - max_loss_pct: rolling max loss
              - loss_trend: 'rising' | 'falling' | 'stable'
              - history: list of measurement dicts in window
        """
        history = self.get_history(target_id)
        if not history:
            return {
                "count": 0,
                "current_latency_ms": None,
                "avg_latency_ms": None,
                "min_latency_ms": None,
                "max_latency_ms": None,
                "latency_trend": "stable",
                "current_loss_pct": None,
                "avg_loss_pct": None,
                "min_loss_pct": None,
                "max_loss_pct": None,
                "loss_trend": "stable",
                "history": [],
            }

        latencies = [
            float(m["latency_ms"])
            for m in history
            if m["latency_ms"] is not None and m["status"] != "down"
        ]
        losses = [float(m["loss_pct"]) for m in history if m["loss_pct"] is not None]

        # Latency statistics
        if latencies:
            current_lat = latencies[-1]
            avg_lat = round(sum(latencies) / len(latencies), 2)
            min_lat = round(min(latencies), 2)
            max_lat = round(max(latencies), 2)
            lat_trend = self._compute_direction(latencies, rel_threshold=0.15, abs_threshold=1.0)
        else:
            current_lat = None
            avg_lat = None
            min_lat = None
            max_lat = None
            lat_trend = "stable"

        # Packet loss statistics
        if losses:
            current_loss = losses[-1]
            avg_loss = round(sum(losses) / len(losses), 3)
            min_loss = round(min(losses), 3)
            max_loss = round(max(losses), 3)
            loss_trend = self._compute_direction(losses, rel_threshold=0.20, abs_threshold=0.5)
        else:
            current_loss = None
            avg_loss = None
            min_loss = None
            max_loss = None
            loss_trend = "stable"

        return {
            "count": len(history),
            "current_latency_ms": current_lat,
            "avg_latency_ms": avg_lat,
            "min_latency_ms": min_lat,
            "max_latency_ms": max_lat,
            "latency_trend": lat_trend,
            "current_loss_pct": current_loss,
            "avg_loss_pct": avg_loss,
            "min_loss_pct": min_loss,
            "max_loss_pct": max_loss,
            "loss_trend": loss_trend,
            "history": history,
        }

    @staticmethod
    def _compute_direction(
        series: List[float], rel_threshold: float = 0.15, abs_threshold: float = 1.0
    ) -> str:
        """Determine whether a numerical time series is rising, falling, or stable."""
        if len(series) < 2:
            return "stable"

        k = max(1, min(3, len(series) // 3))
        recent_median = median(series[-k:])
        earlier_median = median(series[:-k])
        delta = recent_median - earlier_median

        if abs(delta) < abs_threshold:
            return "stable"

        if earlier_median == 0:
            return "rising" if delta > 0 else "falling"

        rel_change = delta / earlier_median

        if rel_change >= rel_threshold:
            return "rising"
        if rel_change <= -rel_threshold:
            return "falling"
        return "stable"

    def clear(self) -> None:
        """Clear all stored window history."""
        self._windows.clear()
