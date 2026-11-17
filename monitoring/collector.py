"""Telemetry collector for NetPulse AI.

Polls the network simulator on a schedule and records latency,
packet loss, and node health into SQLite via the database module.
"""

from datetime import datetime, timezone
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Union

# Enable direct script execution
if __name__ == "__main__" and __package__ is None:
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

from database.db import (
    DEFAULT_DB_PATH,
    init_db,
    insert_measurements,
    query_measurements,
)

logger = logging.getLogger("netpulse.collector")


class Collector:
    """Telemetry collector that polls network simulator and stores measurements in SQLite.

    Parameters:
        simulator: Simulator instance providing tick() or get_measurements().
        poll_interval: Interval between consecutive polls in seconds. Default 5.0.
        db_path: Optional path to SQLite database. Default data/netpulse.db.
    """

    def __init__(
        self,
        simulator: Any,
        poll_interval: float = 5.0,
        db_path: Optional[Union[str, Path]] = None,
    ) -> None:
        self.simulator = simulator
        self.poll_interval = float(poll_interval)
        self.db_path = db_path if db_path is not None else DEFAULT_DB_PATH
        self._stop_requested = False
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
        """Signal the running collector loop to terminate."""
        self._stop_requested = True

    def run(self, duration_seconds: float) -> int:
        """Run the collection loop for a fixed duration.

        Args:
            duration_seconds: Maximum total duration to run the collector in seconds.

        Returns:
            Total number of poll cycles executed.
        """
        start_time = time.monotonic()
        total_polls = 0

        while not self._stop_requested and (time.monotonic() - start_time) < duration_seconds:
            self.collect_once()
            total_polls += 1

            elapsed = time.monotonic() - start_time
            remaining = duration_seconds - elapsed
            if remaining <= 0 or self._stop_requested:
                break

            sleep_time = min(self.poll_interval, remaining)
            time.sleep(sleep_time)

        # Reset stop flag for future runs
        self._stop_requested = False
        return total_polls


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    from network.simulator import Simulator

    print("=" * 65)
    print("NetPulse AI — Telemetry Collector Demo")
    print("=" * 65)

    sim = Simulator(seed=42)
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
