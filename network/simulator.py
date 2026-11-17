"""Network simulator for NetPulse AI.

Simulates synthetic ISP infrastructure, advances time via ticks,
generates periodic telemetry measurements for nodes and links,
and supports fault injection (congestion, node failure, flapping).
"""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import random
import sys
from typing import Any, Dict, List, Optional, Tuple, Union
import networkx as nx

# Enable direct script execution if executed as python network/simulator.py
if __name__ == "__main__" and __package__ is None:
    repo_root = str(Path(__file__).resolve().parent.parent)
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

try:
    from .topology import build_topology
except ImportError:
    from network.topology import build_topology


class Simulator:
    """Network Simulator for synthetic ISP network.

    Parameters:
      topology: Optional nx.Graph. If None, builds default ISP topology.
      seed: Optional int random seed for deterministic simulation. Default 42.
      base_time: Optional datetime or ISO string for simulation clock.
                 Default is 2026-11-18T00:00:00Z.
      step_interval_seconds: Seconds between consecutive ticks. Default 10.
    """

    def __init__(
        self,
        topology: Optional[nx.Graph] = None,
        seed: Optional[int] = 42,
        base_time: Optional[Union[datetime, str]] = None,
        step_interval_seconds: int = 10,
    ) -> None:
        self.graph: nx.Graph = topology if topology is not None else build_topology()
        self.seed = seed
        self.rng = random.Random(seed)
        self.step_interval_seconds = step_interval_seconds
        self.step_count: int = 0

        # Base timestamp for deterministic simulation runs
        if base_time is None:
            self.base_time = datetime(2026, 11, 18, 0, 0, 0, tzinfo=timezone.utc)
        elif isinstance(base_time, str):
            self.base_time = datetime.fromisoformat(base_time)
            if self.base_time.tzinfo is None:
                self.base_time = self.base_time.replace(tzinfo=timezone.utc)
        elif isinstance(base_time, datetime):
            if base_time.tzinfo is None:
                self.base_time = base_time.replace(tzinfo=timezone.utc)
            else:
                self.base_time = base_time
        else:
            raise TypeError("base_time must be a datetime, an ISO format string, or None")

        # Map edge representations to canonical link IDs
        self._link_lookup: Dict[Any, str] = {}
        self._canonical_links: List[Tuple[str, str, str, Dict[str, Any]]] = []
        self._init_link_mappings()

        # Active faults: canonical_id -> dict
        # { 'kind': str, 'target_type': 'node'|'link', 'target_id': str,
        #   'duration': int|None, 'remaining_ticks': int|None }
        self.active_faults: Dict[str, Dict[str, Any]] = {}

        # Cached latest measurements
        self._latest_measurements: Optional[List[Dict[str, Any]]] = None

    def _init_link_mappings(self) -> None:
        """Initialize bidirectional lookup and canonical IDs for all edges."""
        self._link_lookup.clear()
        self._canonical_links.clear()

        for u, v, data in self.graph.edges(data=True):
            # Canonical ID follows u-v
            canonical_id = f"{u}-{v}"
            self._canonical_links.append((canonical_id, u, v, data))

            # Populate lookup entries
            self._link_lookup[(u, v)] = canonical_id
            self._link_lookup[(v, u)] = canonical_id
            self._link_lookup[canonical_id] = canonical_id
            self._link_lookup[f"{v}-{u}"] = canonical_id
            self._link_lookup[f"{u}--{v}"] = canonical_id
            self._link_lookup[f"{v}--{u}"] = canonical_id

    def _resolve_target(self, target: Any) -> Tuple[str, str]:
        """Resolve target to (target_type, canonical_id).

        Returns:
            Tuple of ('node' | 'link', canonical_id)

        Raises:
            ValueError if target does not exist.
        """
        # Check node
        if isinstance(target, str) and target in self.graph.nodes:
            return "node", target

        # Check link in lookup
        if target in self._link_lookup:
            return "link", self._link_lookup[target]

        # Check tuple (u, v)
        if isinstance(target, tuple) and len(target) == 2:
            u, v = target
            if (u, v) in self._link_lookup:
                return "link", self._link_lookup[(u, v)]

        # Check string with separator
        if isinstance(target, str):
            for sep in ("--", "-", "->", "<->"):
                if sep in target:
                    parts = target.split(sep, 1)
                    cand = (parts[0].strip(), parts[1].strip())
                    if cand in self._link_lookup:
                        return "link", self._link_lookup[cand]

        raise ValueError(f"Target '{target}' not found in topology nodes or links.")

    def inject_fault(
        self,
        kind: str,
        target: Any,
        duration: Optional[int] = None,
    ) -> None:
        """Inject a fault into a node or link.

        Args:
            kind: 'congestion' | 'node_down' | 'flapping'
            target: Node ID (str) or Link ID (tuple or str, e.g. ('core_1', 'dist_1') or 'core_1-dist_1')
            duration: Number of ticks this fault remains active.
                      If None, lasts indefinitely until clear_fault() is called.
        """
        valid_kinds = {"congestion", "node_down", "flapping"}
        if kind not in valid_kinds:
            raise ValueError(
                f"Unknown fault kind '{kind}'. Valid kinds are: {', '.join(sorted(valid_kinds))}"
            )

        if duration is not None and duration <= 0:
            raise ValueError("duration must be a positive integer or None")

        target_type, canonical_id = self._resolve_target(target)

        if kind == "node_down" and target_type != "node":
            raise ValueError(
                f"Fault 'node_down' can only be injected on a node, got {target_type} '{target}'."
            )

        if kind in ("congestion", "flapping") and target_type != "link":
            raise ValueError(
                f"Fault '{kind}' can only be injected on a link, got {target_type} '{target}'."
            )

        self.active_faults[canonical_id] = {
            "kind": kind,
            "target_type": target_type,
            "target_id": canonical_id,
            "duration": duration,
            "remaining_ticks": duration,
        }

    def clear_fault(self, target: Any) -> bool:
        """Clear an active fault on target.

        Returns:
            True if an active fault was cleared, False otherwise.
        """
        try:
            _, canonical_id = self._resolve_target(target)
        except ValueError:
            return False

        if canonical_id in self.active_faults:
            del self.active_faults[canonical_id]
            return True
        return False

    def clear_all_faults(self) -> None:
        """Clear all active faults across all nodes and links."""
        self.active_faults.clear()

    @property
    def current_timestamp(self) -> str:
        """Return the current simulation timestamp in ISO 8601 format."""
        elapsed = timedelta(seconds=self.step_count * self.step_interval_seconds)
        current_dt = self.base_time + elapsed
        return current_dt.isoformat()

    def tick(self) -> List[Dict[str, Any]]:
        """Advance the simulation by one step and return measurements.

        Decrements fault durations and expires finished faults after measuring.
        """
        self.step_count += 1

        # Generate measurements for the new step
        measurements = self._generate_measurements()
        self._latest_measurements = measurements

        # Decrement remaining ticks for active faults and remove expired
        expired = []
        for target_id, fault in self.active_faults.items():
            if fault["remaining_ticks"] is not None:
                fault["remaining_ticks"] -= 1
                if fault["remaining_ticks"] <= 0:
                    expired.append(target_id)

        for target_id in expired:
            del self.active_faults[target_id]

        return measurements

    def get_measurements(self) -> List[Dict[str, Any]]:
        """Return measurements for current step.

        If tick() has not been called yet, generates initial step-0 measurements.
        """
        if self._latest_measurements is None:
            self._latest_measurements = self._generate_measurements()
        return self._latest_measurements

    def _generate_measurements(self) -> List[Dict[str, Any]]:
        """Generate measurements for all nodes and links at current step."""
        timestamp = self.current_timestamp
        measurements: List[Dict[str, Any]] = []

        # 1. Node measurements
        for node_id, data in self.graph.nodes(data=True):
            fault = self.active_faults.get(node_id)
            if fault and fault["kind"] == "node_down":
                status = "down"
                loss_pct = 100.0
                latency_ms = 0.0
            else:
                status = data.get("status", "up")
                # Healthy node baseline: low latency, minimal loss (< 0.5%)
                latency_ms = round(self.rng.uniform(0.8, 1.2), 2)
                loss_pct = round(self.rng.uniform(0.0, 0.1), 3)

            measurements.append(
                {
                    "timestamp": timestamp,
                    "target_type": "node",
                    "target_id": node_id,
                    "latency_ms": latency_ms,
                    "loss_pct": loss_pct,
                    "status": status,
                }
            )

        # 2. Link measurements
        for canonical_id, u, v, data in self._canonical_links:
            base_latency = data.get("latency_ms", 15.0)
            fault = self.active_faults.get(canonical_id)

            if fault and fault["kind"] == "congestion":
                # Congestion: latency ~5x baseline, link status up
                status = "up"
                latency_jitter = self.rng.uniform(0.98, 1.02)
                latency_ms = round(base_latency * 5.0 * latency_jitter, 2)
                # Congestion causes slight packet drop, but link is still up
                loss_pct = round(self.rng.uniform(1.0, 3.5), 3)

            elif fault and fault["kind"] == "flapping":
                # Flapping: link alternates up/down per tick
                # Odd step: down (100% loss); Even step: up (normal latency & loss)
                if self.step_count % 2 == 1:
                    status = "down"
                    loss_pct = 100.0
                    latency_ms = 0.0
                else:
                    status = "up"
                    loss_pct = round(self.rng.uniform(0.0, 0.2), 3)
                    latency_ms = round(base_latency * self.rng.uniform(0.95, 1.05), 2)

            else:
                # Healthy link baseline: ~5ms core, ~15ms dist, ~30ms access
                status = data.get("status", "up")
                latency_ms = round(base_latency * self.rng.uniform(0.95, 1.05), 2)
                loss_pct = round(self.rng.uniform(0.0, 0.25), 3)

            measurements.append(
                {
                    "timestamp": timestamp,
                    "target_type": "link",
                    "target_id": canonical_id,
                    "latency_ms": latency_ms,
                    "loss_pct": loss_pct,
                    "status": status,
                }
            )

        return measurements


if __name__ == "__main__":
    print("=" * 60)
    print("NetPulse AI — Network Simulator Demo")
    print("=" * 60)

    sim = Simulator(seed=42)
    print(f"Nodes in simulation: {sim.graph.number_of_nodes()}")
    print(f"Links in simulation: {sim.graph.number_of_edges()}")

    # Baseline tick
    print("\n[Step 1] Baseline Healthy Network Tick:")
    m1 = sim.tick()
    core_link_m = next(m for m in m1 if m["target_id"] == "core_1-core_2")
    dist_node_m = next(m for m in m1 if m["target_id"] == "dist_1")
    print(f"  core_1-core_2 link: latency={core_link_m['latency_ms']}ms, loss={core_link_m['loss_pct']}%, status={core_link_m['status']}")
    print(f"  dist_1 node:        latency={dist_node_m['latency_ms']}ms, loss={dist_node_m['loss_pct']}%, status={dist_node_m['status']}")

    # Inject congestion fault on core_1-dist_1
    print("\n[Step 2] Injecting Congestion on core_1-dist_1 for 2 ticks...")
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=2)
    m2 = sim.tick()
    cong_m = next(m for m in m2 if m["target_id"] == "core_1-dist_1")
    print(f"  core_1-dist_1: latency={cong_m['latency_ms']}ms (baseline ~15ms -> ~5x), loss={cong_m['loss_pct']}%, status={cong_m['status']}")

    # Inject node_down fault on dist_2
    print("\n[Step 3] Injecting node_down on dist_2...")
    sim.inject_fault("node_down", "dist_2", duration=2)
    m3 = sim.tick()
    down_m = next(m for m in m3 if m["target_id"] == "dist_2")
    print(f"  dist_2 node: status={down_m['status']}, loss={down_m['loss_pct']}%")

    # Clear faults and verify recovery
    print("\n[Step 4] Advancing past fault durations (verifying auto-recovery):")
    m4 = sim.tick()
    m5 = sim.tick()
    cong_recovered = next(m for m in m5 if m["target_id"] == "core_1-dist_1")
    down_recovered = next(m for m in m5 if m["target_id"] == "dist_2")
    print(f"  core_1-dist_1: latency={cong_recovered['latency_ms']}ms, loss={cong_recovered['loss_pct']}%, status={cong_recovered['status']}")
    print(f"  dist_2 node:   latency={down_recovered['latency_ms']}ms, loss={down_recovered['loss_pct']}%, status={down_recovered['status']}")
    print("=" * 60)
