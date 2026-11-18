"""Network telemetry monitor for NetPulse AI.

Integrates threshold evaluation rules with rolling trend tracking,
queries historical telemetry from SQLite, and exposes real-time
network and target health status for the Streamlit dashboard.
"""

from datetime import datetime, timezone
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from database.db import DEFAULT_DB_PATH, list_target_ids, query_measurements
from monitoring.rules import (
    Breach,
    ThresholdConfig,
    evaluate_measurement,
    get_target_tier,
)
from monitoring.trends import RollingTrendTracker


class NetworkMonitor:
    """Monitors telemetry measurements, evaluates threshold rules, tracks rolling trends,

    and exposes current status and active breaches for the dashboard.

    Parameters:
        thresholds: Optional ThresholdConfig instance.
        window_size: Number of rolling measurements per target to retain for trend analysis.
                     Default 20.
        db_path: Optional path to SQLite database. Default data/netpulse.db.
    """

    def __init__(
        self,
        thresholds: Optional[ThresholdConfig] = None,
        window_size: int = 20,
        db_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.thresholds = thresholds if thresholds is not None else ThresholdConfig()
        self.tracker = RollingTrendTracker(window_size=window_size)
        self.db_path = db_path if db_path is not None else DEFAULT_DB_PATH
        # Cached target state: target_id -> dict
        self._target_states: Dict[str, Dict[str, Any]] = {}
        # Active breaches per target: target_id -> List[Breach]
        self._active_breaches: Dict[str, List[Breach]] = {}
        self._last_evaluated_timestamp: Optional[str] = None

    def record_measurement(self, measurement: Dict[str, Any]) -> List[Breach]:
        """Record and evaluate a single measurement dict.

        Args:
            measurement: Dict with keys: timestamp, target_type, target_id,
                         latency_ms, loss_pct, status.

        Returns:
            List of Breach objects triggered by this measurement.
        """
        target_id = str(measurement["target_id"])
        target_type = str(measurement.get("target_type", "link"))
        tier = get_target_tier(target_id, target_type)

        # 1. Update rolling trend tracker
        self.tracker.add_measurement(measurement)

        # 2. Evaluate thresholds and status
        breaches = evaluate_measurement(measurement, self.thresholds, tier=tier)
        self._active_breaches[target_id] = breaches

        # 3. Determine target health level
        if any(b.severity == "CRITICAL" for b in breaches):
            health = "CRITICAL"
        elif any(b.severity == "WARNING" for b in breaches):
            health = "WARNING"
        else:
            health = "HEALTHY"

        trend = self.tracker.get_trend(target_id)
        timestamp = str(measurement.get("timestamp", ""))
        self._last_evaluated_timestamp = timestamp

        # 4. Cache detailed target status
        self._target_states[target_id] = {
            "target_id": target_id,
            "target_type": target_type,
            "tier": tier,
            "status": str(measurement.get("status", "up")),
            "health": health,
            "is_breaching": len(breaches) > 0,
            "timestamp": timestamp,
            "current_latency_ms": (
                None
                if str(measurement.get("status", "up")).lower() == "down"
                else measurement.get("latency_ms")
            ),
            "current_loss_pct": measurement.get("loss_pct"),
            "rolling_avg_latency_ms": trend["avg_latency_ms"],
            "rolling_min_latency_ms": trend["min_latency_ms"],
            "rolling_max_latency_ms": trend["max_latency_ms"],
            "latency_trend": trend["latency_trend"],
            "rolling_avg_loss_pct": trend["avg_loss_pct"],
            "rolling_min_loss_pct": trend["min_loss_pct"],
            "rolling_max_loss_pct": trend["max_loss_pct"],
            "loss_trend": trend["loss_trend"],
            "breaches": [b.to_dict() for b in breaches],
            "recent_trend": trend,
            "recent_history": trend["history"],
        }

        return breaches

    def record_measurements(self, measurements: List[Dict[str, Any]]) -> List[Breach]:
        """Batch record and evaluate multiple measurements (e.g. from a simulation tick or poll).

        Returns:
            List of all Breach objects triggered across the batch.
        """
        all_breaches: List[Breach] = []
        for m in measurements:
            all_breaches.extend(self.record_measurement(m))
        return all_breaches

    def get_target_status(self, target_id: str) -> Optional[Dict[str, Any]]:
        """Return the current monitoring status and recent trend for a specific target.

        Returns:
            Status dictionary or None if target has not been observed.
        """
        state = self._target_states.get(target_id)
        return deepcopy(state) if state is not None else None

    def get_network_status(self) -> Dict[str, Any]:
        """Return a network-wide summary for dashboard rendering.

        Returns:
            Dictionary containing overall health, counts, list of breaching targets,
            and map of all target statuses.
        """
        total = len(self._target_states)
        healthy = 0
        warning = 0
        critical = 0
        breaching_target_ids: List[str] = []
        all_active_breaches: List[Dict[str, Any]] = []

        for tid, state in self._target_states.items():
            h = state["health"]
            if h == "CRITICAL":
                critical += 1
                breaching_target_ids.append(tid)
            elif h == "WARNING":
                warning += 1
                breaching_target_ids.append(tid)
            else:
                healthy += 1

            all_active_breaches.extend(state["breaches"])

        if critical > 0:
            overall = "CRITICAL"
        elif warning > 0:
            overall = "WARNING"
        else:
            overall = "HEALTHY"

        status = {
            "timestamp": self._last_evaluated_timestamp or datetime.now(timezone.utc).isoformat(),
            "overall_health": overall,
            "total_targets": total,
            "healthy_count": healthy,
            "warning_count": warning,
            "critical_count": critical,
            "breaching_targets": breaching_target_ids,
            "active_breaches": all_active_breaches,
            "targets": self._target_states,
        }
        return deepcopy(status)

    def get_breaching_targets(self) -> List[Dict[str, Any]]:
        """Return status dictionaries for all targets currently in a breaching state.

        Sorted by severity (CRITICAL before WARNING) then by target_id.
        """
        breaching = [
            state for state in self._target_states.values() if state["is_breaching"]
        ]
        # Sort CRITICAL first, then WARNING
        breaching = sorted(
            breaching,
            key=lambda s: (0 if s["health"] == "CRITICAL" else 1, s["target_id"]),
        )
        return deepcopy(breaching)

    def get_all_breaches(self) -> List[Dict[str, Any]]:
        """Return all active breach records across all targets."""
        breaches: List[Dict[str, Any]] = []
        for state in self._target_states.values():
            breaches.extend(state["breaches"])
        return deepcopy(breaches)

    def load_from_db(
        self,
        target_id: Optional[str] = None,
        window_size: Optional[int] = None,
        db_path: Optional[Union[str, Path]] = None,
    ) -> int:
        """Query historical measurements from SQLite database to populate trends and state.

        Args:
            target_id: Optional target ID to filter by.
            window_size: Maximum measurements to retrieve per target. Default self.tracker.window_size.
            db_path: Optional database path. Defaults to self.db_path.

        Returns:
            Number of measurement rows ingested.
        """
        path = db_path if db_path is not None else self.db_path
        limit_size = window_size if window_size is not None else self.tracker.window_size
        if isinstance(limit_size, bool) or (
            not isinstance(limit_size, int) or limit_size < 0
        ):
            raise ValueError("window_size must be None or a non-negative integer")

        if target_id is not None:
            # Query recent measurements for specific target
            rows = query_measurements(
                target_id=target_id,
                path=path,
                order="DESC",
                limit=limit_size,
            )
            # Reverse to chronological order (ASC)
            rows.reverse()
            self.record_measurements(rows)
            return len(rows)

        target_ids = list_target_ids(path)
        if not target_ids:
            return 0

        total_rows = 0
        for loaded_target_id in target_ids:
            rows = query_measurements(
                target_id=loaded_target_id,
                path=path,
                order="DESC",
                limit=limit_size,
            )
            rows.reverse()
            self.record_measurements(rows)
            total_rows += len(rows)
        return total_rows

    @classmethod
    def from_db(
        cls,
        db_path: Optional[Union[str, Path]] = None,
        thresholds: Optional[ThresholdConfig] = None,
        window_size: int = 20,
    ) -> "NetworkMonitor":
        """Instantiate a NetworkMonitor pre-populated with recent telemetry from SQLite.

        Args:
            db_path: Path to SQLite database. Defaults to DEFAULT_DB_PATH.
            thresholds: Optional ThresholdConfig instance.
            window_size: Rolling window size. Default 20.

        Returns:
            Configured and populated NetworkMonitor ready for dashboard queries.
        """
        monitor = cls(thresholds=thresholds, window_size=window_size, db_path=db_path)
        monitor.load_from_db()
        return monitor

    def reset(self) -> None:
        """Clear all active states, breaches, and rolling window trends."""
        self.tracker.clear()
        self._target_states.clear()
        self._active_breaches.clear()
        self._last_evaluated_timestamp = None


if __name__ == "__main__":
    from network.simulator import Simulator

    print("=" * 70)
    print("NetPulse AI — Monitoring Rules & Trends Demo (python -m monitoring.monitor)")
    print("=" * 70)

    sim = Simulator(seed=42)
    monitor = NetworkMonitor(window_size=10)

    # 1. Warm up with 3 healthy ticks
    print("\n[Step 1] Feeding 3 healthy simulation ticks...")
    for _ in range(3):
        monitor.record_measurements(sim.tick())

    net_status = monitor.get_network_status()
    print(f"  Overall Network Health: {net_status['overall_health']}")
    print(f"  Healthy: {net_status['healthy_count']} | Warning: {net_status['warning_count']} | Critical: {net_status['critical_count']}")
    print(f"  Breaching targets: {len(net_status['breaching_targets'])}")

    # 2. Inject congestion on core_1-dist_1 (baseline ~15ms -> ~75ms)
    print("\n[Step 2] Injecting Congestion fault on 'core_1-dist_1' (latency x5)...")
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=2)
    monitor.record_measurements(sim.tick())

    target_status = monitor.get_target_status("core_1-dist_1")
    critical_threshold = monitor.thresholds.get_thresholds_for_target(
        "core_1-dist_1", "link", "distribution"
    )["latency_crit_ms"]
    print(f"\n[Step 3] Status for 'core_1-dist_1':")
    print(f"  Health:          {target_status['health']}")
    print(f"  Is Breaching:    {target_status['is_breaching']}")
    print(f"  Current Latency: {target_status['current_latency_ms']} ms (threshold: {critical_threshold:.1f} ms)")
    print(f"  Latency Trend:   {target_status['latency_trend']}")
    print(f"  Rolling Avg:     {target_status['rolling_avg_latency_ms']} ms")
    print(f"  Active Breaches:")
    for b in target_status["breaches"]:
        print(f"    - [{b['severity']}] {b['message']}")

    print("\nRecent measurements trend history:")
    for point in target_status["recent_history"]:
        print(f"    {point['timestamp']} | latency={point['latency_ms']}ms | loss={point['loss_pct']}% | status={point['status']}")

    # 3. Recovery
    print("\n[Step 4] Advancing simulation to fault expiry and recovery...")
    sim.tick()
    monitor.record_measurements(sim.tick())
    recovered = monitor.get_target_status("core_1-dist_1")
    print(f"  Recovered Health:        {recovered['health']}")
    print(f"  Recovered Latency:       {recovered['current_latency_ms']} ms")
    print(f"  Recovered Latency Trend: {recovered['latency_trend']}")
    print("=" * 70)
