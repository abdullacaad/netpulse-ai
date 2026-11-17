"""Telemetry collector for NetPulse AI.

Polls the network simulator on a schedule and records latency,
packet loss, and node health into SQLite via the database module.
"""

from datetime import datetime, timezone
import logging
import math
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Union

from database.db import (
    DEFAULT_DB_PATH,
    init_db,
    insert_measurements,
    query_measurements,
)

logger = logging.getLogger("netpulse.collector")


class Collector:
    """Telemetry collector that polls network simulator and stores measurements in SQLite.

    Polling Contract:
        tick() is preferred and advances the simulation clock. If the source only
        implements get_measurements(), the caller or source must advance time itself.
        The collector owns the simulation clock when running against a Simulator;
        having a second consumer call tick() concurrently would double-advance it.

    Parameters:
        simulator: Simulator instance providing tick() or get_measurements().
        poll_interval: Interval between consecutive polls in seconds. Default 5.0.
                       Must be a positive, finite number.
        db_path: Optional path to SQLite database. Default data/netpulse.db.
    """

    def __init__(
        self,
        simulator: Any,
        poll_interval: float = 5.0,
        db_path: Optional[Union[str, Path]] = None,
    ) -> None:
        try:
            val = float(poll_interval)
        except (TypeError, ValueError) as e:
            raise ValueError(f"poll_interval must be a positive finite number, got {poll_interval}") from e

        if math.isnan(val) or math.isinf(val) or val <= 0:
            raise ValueError(f"poll_interval must be a positive finite number, got {poll_interval}")

        self.simulator = simulator
        self.poll_interval = val
        self.db_path = db_path if db_path is not None else DEFAULT_DB_PATH
        self._stop_event = threading.Event()
        self.logger = logger

        # Ensure database and table are initialized
        init_db(self.db_path)

    def collect_once(self) -> List[Dict[str, Any]]:
        """Poll the simulator once and store the measurements in the database.

        If polling or storage fails, logs the error and returns an empty list
        without crashing the caller.

        Returns:
            List of measurement dicts collected and stored, or [] on failure.
        """
        try:
            if hasattr(self.simulator, "tick"):
                rows = self.simulator.tick()
            elif hasattr(self.simulator, "get_measurements"):
                rows = self.simulator.get_measurements()
            else:
                raise AttributeError("Simulator must implement tick() or get_measurements()")

            if rows:
                insert_measurements(rows, self.db_path)
            return rows
        except Exception as e:
            self.logger.error("Error during telemetry collection poll: %s", e, exc_info=True)
            return []

    def stop(self) -> None:
        """Signal the running collector loop to terminate immediately."""
        self._stop_event.set()

    def run(self, duration_seconds: float) -> int:
        """Run the collection loop for a fixed duration.

        Args:
            duration_seconds: Maximum total duration to run the collector in seconds.

        Returns:
            Total number of poll cycles executed.
        """
        start_time = time.monotonic()
        total_polls = 0

        while not self._stop_event.is_set() and (time.monotonic() - start_time) < duration_seconds:
            self.collect_once()
            total_polls += 1

            elapsed = time.monotonic() - start_time
            remaining = duration_seconds - elapsed
            if remaining <= 0 or self._stop_event.is_set():
                break

            sleep_time = min(self.poll_interval, remaining)
            # Returns True if stop_event was signaled, False on timeout
            if self._stop_event.wait(timeout=sleep_time):
                break

        # Reset stop event for future runs
        self._stop_event.clear()
        return total_polls


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from network.simulator import Simulator

    print("=" * 65)
    print("NetPulse AI — Telemetry Collector Demo (python -m monitoring.collector)")
    print("=" * 65)

    # Pass step_interval_seconds=1 so demo timestamps match wall-clock rate
    sim = Simulator(seed=42, step_interval_seconds=1)
    collector = Collector(simulator=sim, poll_interval=1.0, db_path="data/netpulse.db")

    print("Running collector for 5 seconds (1 poll/sec)...")
    polls = collector.run(duration_seconds=5.0)
    print(f"Collection complete: executed {polls} polls.")

    # Read back measurements from database
    sample = query_measurements(target_id="core_1-dist_1", path="data/netpulse.db")
    print(f"\nRead back {len(sample)} historical measurements for 'core_1-dist_1':")
    for row in sample[-5:]:
        print(f"  {row['timestamp']} | id={row['id']} | latency={row['latency_ms']}ms | loss={row['loss_pct']}% | status={row['status']}")
    print("=" * 65)
