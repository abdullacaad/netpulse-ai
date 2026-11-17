"""Automated test suite for NetPulse AI network simulator and topology."""

from datetime import datetime, timezone
from pathlib import Path
import sys
import networkx as nx
import pytest

# Ensure repository root is on sys.path in all environments
repo_root = str(Path(__file__).resolve().parent.parent)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from network import (
    build_topology,
    get_links_by_type,
    get_nodes_by_type,
    get_topology_summary,
    Simulator,
)


# ============================================================================
# Topology Tests
# ============================================================================


def test_topology_node_counts():
    """Verify topology contains exact required node counts for each tier."""
    graph = build_topology()

    core_nodes = get_nodes_by_type(graph, "core")
    dist_nodes = get_nodes_by_type(graph, "distribution")
    access_nodes = get_nodes_by_type(graph, "access")
    cust_nodes = get_nodes_by_type(graph, "customer")

    assert len(core_nodes) == 2, f"Expected 2 core routers, got {len(core_nodes)}"
    assert len(dist_nodes) == 4, f"Expected 4 distribution nodes, got {len(dist_nodes)}"
    assert len(access_nodes) == 8, f"Expected 8 access nodes, got {len(access_nodes)}"
    assert len(cust_nodes) == 16, f"Expected 16 customer endpoints, got {len(cust_nodes)}"
    assert graph.number_of_nodes() == 30, f"Expected 30 total nodes, got {graph.number_of_nodes()}"


def test_topology_link_counts():
    """Verify topology contains exact required link counts for each tier."""
    graph = build_topology()

    core_links = get_links_by_type(graph, "core")
    dist_links = get_links_by_type(graph, "distribution")
    access_links = get_links_by_type(graph, "access")
    cust_links = get_links_by_type(graph, "customer")

    assert len(core_links) == 1, f"Expected 1 core-to-core link, got {len(core_links)}"
    assert len(dist_links) == 4, f"Expected 4 core-to-distribution links, got {len(dist_links)}"
    assert len(access_links) == 8, f"Expected 8 distribution-to-access links, got {len(access_links)}"
    assert len(cust_links) == 16, f"Expected 16 access-to-customer links, got {len(cust_links)}"
    assert graph.number_of_edges() == 29, f"Expected 29 total links, got {graph.number_of_edges()}"


def test_topology_is_connected():
    """Verify synthetic ISP network forms a single connected graph."""
    graph = build_topology()
    assert nx.is_connected(graph), "Topology must be a fully connected graph"


def test_topology_node_attributes():
    """Verify required attributes on all nodes: type, name, status."""
    graph = build_topology()
    valid_types = {"core", "distribution", "access", "customer"}

    for node_id, attrs in graph.nodes(data=True):
        assert "type" in attrs, f"Node {node_id} missing 'type' attribute"
        assert attrs["type"] in valid_types, f"Node {node_id} has invalid type: {attrs['type']}"
        assert attrs.get("name") == node_id, f"Node {node_id} 'name' does not match id"
        assert attrs.get("status") == "up", f"Node {node_id} initial status should be 'up'"


def test_topology_edge_attributes_and_baselines():
    """Verify baseline behaviour on edges: core ~5ms, dist ~15ms, access ~30ms, loss < 0.5%."""
    graph = build_topology()

    for u, v, attrs in graph.edges(data=True):
        assert "latency_ms" in attrs, f"Edge ({u}, {v}) missing 'latency_ms'"
        assert "loss_pct" in attrs, f"Edge ({u}, {v}) missing 'loss_pct'"
        assert "capacity_mbps" in attrs, f"Edge ({u}, {v}) missing 'capacity_mbps'"
        assert attrs.get("status") == "up", f"Edge ({u}, {v}) initial status should be 'up'"

        # Loss under 0.5% when healthy
        assert attrs["loss_pct"] < 0.5, f"Edge ({u}, {v}) baseline loss should be < 0.5%"

        # Check expected baseline latencies per link type
        link_type = attrs.get("link_type")
        if link_type == "core":
            assert attrs["latency_ms"] == pytest.approx(5.0, abs=1.0)
            assert attrs["capacity_mbps"] == 10000
        elif link_type == "distribution":
            assert attrs["latency_ms"] == pytest.approx(15.0, abs=2.0)
            assert attrs["capacity_mbps"] == 1000
        elif link_type in ("access", "customer"):
            assert attrs["latency_ms"] == pytest.approx(30.0, abs=3.0)
            assert attrs["capacity_mbps"] == 100


def test_get_topology_summary():
    """Verify get_topology_summary returns all expected key counts."""
    graph = build_topology()
    summary = get_topology_summary(graph)

    assert summary["core_nodes"] == 2
    assert summary["distribution_nodes"] == 4
    assert summary["access_nodes"] == 8
    assert summary["customer_nodes"] == 16
    assert summary["total_nodes"] == 30
    assert summary["core_links"] == 1
    assert summary["distribution_links"] == 4
    assert summary["access_links"] == 8
    assert summary["customer_links"] == 16
    assert summary["total_links"] == 29


# ============================================================================
# Simulator Measurement & Interface Tests
# ============================================================================


def test_simulator_measurement_schema():
    """Verify get_measurements schema: timestamp, target_type, target_id, latency_ms, loss_pct, status."""
    sim = Simulator(seed=42)
    measurements = sim.get_measurements()

    # Total measurements = 30 nodes + 29 links = 59
    assert len(measurements) == 59, f"Expected 59 measurements, got {len(measurements)}"

    node_count = 0
    link_count = 0

    for m in measurements:
        assert "timestamp" in m
        assert "target_type" in m
        assert "target_id" in m
        assert "latency_ms" in m
        assert "loss_pct" in m
        assert "status" in m

        assert m["target_type"] in ("node", "link")
        assert m["status"] in ("up", "down")
        assert isinstance(m["latency_ms"], (int, float))
        assert isinstance(m["loss_pct"], (int, float))
        assert isinstance(m["target_id"], str)

        # Verify timestamp is valid ISO string
        datetime.fromisoformat(m["timestamp"])

        if m["target_type"] == "node":
            node_count += 1
            assert m["loss_pct"] < 0.5
            assert m["status"] == "up"
        else:
            link_count += 1
            assert m["loss_pct"] < 0.5
            assert m["status"] == "up"

    assert node_count == 30
    assert link_count == 29


def test_simulator_tick_advances_step():
    """Verify tick() advances step counter and simulation timestamp."""
    sim = Simulator(seed=42, step_interval_seconds=10)
    assert sim.step_count == 0

    initial_time = sim.current_timestamp
    m1 = sim.tick()
    assert sim.step_count == 1
    tick1_time = sim.current_timestamp
    assert tick1_time != initial_time
    assert len(m1) == 59

    m2 = sim.tick()
    assert sim.step_count == 2
    assert sim.current_timestamp != tick1_time
    assert len(m2) == 59


# ============================================================================
# Seed & Reproducibility Tests
# ============================================================================


def test_simulator_reproducible_seed():
    """Verify two Simulator instances with identical seeds produce identical measurements."""
    base_time = "2026-11-18T00:00:00Z"
    sim1 = Simulator(seed=42, base_time=base_time)
    sim2 = Simulator(seed=42, base_time=base_time)

    # Initial measurements before tick
    assert sim1.get_measurements() == sim2.get_measurements()

    # Across multiple ticks
    for step in range(5):
        m1 = sim1.tick()
        m2 = sim2.tick()
        assert m1 == m2, f"Mismatch at step {step + 1} with seed=42"


def test_simulator_default_base_time_is_utc_now():
    """Verify Simulator defaults base_time to current UTC time."""
    before = datetime.now(timezone.utc)
    sim = Simulator(seed=42)
    after = datetime.now(timezone.utc)

    sim_dt = datetime.fromisoformat(sim.current_timestamp)
    assert before <= sim_dt <= after


def test_get_measurements_returns_copies():
    """Verify get_measurements returns a copy, not the internal shared list or mutable dicts."""
    sim = Simulator(seed=42)
    m1 = sim.get_measurements()
    m2 = sim.get_measurements()

    assert m1 is not m2
    assert m1[0] is not m2[0]

    # Mutating returned copy must not mutate internal cached measurements
    m1[0]["status"] = "mutated_status"
    m3 = sim.get_measurements()
    assert m3[0]["status"] != "mutated_status"


def test_simulator_different_seeds_produce_varied_noise():
    """Verify different seeds produce varied jitter in measurements."""
    sim1 = Simulator(seed=42)
    sim2 = Simulator(seed=999)

    m1 = sim1.tick()
    m2 = sim2.tick()

    assert m1 != m2, "Different seeds should produce different jitter values"


# ============================================================================
# Fault Injection Tests
# ============================================================================


def test_fault_congestion_increases_latency_5x():
    """Verify congestion fault increases link latency by ~5x while status remains up."""
    sim = Simulator(seed=42)

    # Baseline healthy tick
    m_baseline = sim.tick()
    base_m = next(m for m in m_baseline if m["target_id"] == "core_1-dist_1")
    baseline_latency = base_m["latency_ms"]
    assert baseline_latency == pytest.approx(15.0, abs=2.0)
    assert base_m["status"] == "up"

    # Inject congestion on core_1-dist_1
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=2)
    m_cong = sim.tick()
    cong_m = next(m for m in m_cong if m["target_id"] == "core_1-dist_1")

    # Latency should be ~5x baseline (~75ms)
    expected_cong_latency = baseline_latency * 5.0
    assert cong_m["latency_ms"] == pytest.approx(expected_cong_latency, rel=0.1)
    assert cong_m["status"] == "up"

    # Other links should remain at normal baseline
    other_m = next(m for m in m_cong if m["target_id"] == "core_1-core_2")
    assert other_m["latency_ms"] == pytest.approx(5.0, abs=1.0)


def test_fault_clear_congestion():
    """Verify clear_fault restores normal baseline latency on a congested link."""
    sim = Simulator(seed=42)

    sim.inject_fault("congestion", "core_1-dist_1")
    m_cong = sim.tick()
    cong_m = next(m for m in m_cong if m["target_id"] == "core_1-dist_1")
    assert cong_m["latency_ms"] > 60.0

    # Clear fault
    cleared = sim.clear_fault("core_1-dist_1")
    assert cleared is True

    m_restored = sim.tick()
    restored_m = next(m for m in m_restored if m["target_id"] == "core_1-dist_1")
    assert restored_m["latency_ms"] == pytest.approx(15.0, abs=2.0)
    assert restored_m["loss_pct"] < 0.5


def test_fault_node_down():
    """Verify node_down fault results in 100% loss and status down."""
    sim = Simulator(seed=42)

    # Normal tick
    m0 = sim.tick()
    dist1_m0 = next(m for m in m0 if m["target_id"] == "dist_1")
    assert dist1_m0["status"] == "up"
    assert dist1_m0["loss_pct"] < 0.5

    # Inject node_down
    sim.inject_fault("node_down", "dist_1", duration=3)
    m1 = sim.tick()
    dist1_m1 = next(m for m in m1 if m["target_id"] == "dist_1")

    assert dist1_m1["status"] == "down"
    assert dist1_m1["loss_pct"] == 100.0

    # Other nodes unaffected
    dist2_m1 = next(m for m in m1 if m["target_id"] == "dist_2")
    assert dist2_m1["status"] == "up"
    assert dist2_m1["loss_pct"] < 0.5


def test_node_down_takes_attached_links_down_and_unattached_stay_up():
    """Verify attached links go down (100% loss, down) on node_down, and unattached links stay up."""
    sim = Simulator(seed=42)

    # dist_1 is attached to core_1-dist_1, dist_1-access_1, dist_1-access_2
    sim.inject_fault("node_down", "dist_1", duration=2)
    m = sim.tick()

    # Check dist_1 node is down
    node_m = next(x for x in m if x["target_id"] == "dist_1")
    assert node_m["status"] == "down"
    assert node_m["loss_pct"] == 100.0

    # Attached links must be down with 100% loss and 0.0 latency
    attached_link_ids = {"core_1-dist_1", "dist_1-access_1", "dist_1-access_2"}
    for link_id in attached_link_ids:
        link_m = next(x for x in m if x["target_id"] == link_id)
        assert link_m["status"] == "down", f"Attached link {link_id} should be down"
        assert link_m["loss_pct"] == 100.0, f"Attached link {link_id} should have 100% loss"
        assert link_m["latency_ms"] == 0.0

    # Unattached links must stay up with normal baseline loss
    unattached_link_ids = {"core_1-core_2", "core_2-dist_3", "dist_2-access_3"}
    for link_id in unattached_link_ids:
        link_m = next(x for x in m if x["target_id"] == link_id)
        assert link_m["status"] == "up", f"Unattached link {link_id} should be up"
        assert link_m["loss_pct"] < 0.5, f"Unattached link {link_id} should have normal loss"


def test_node_down_overrides_congestion_on_attached_link_and_recovers_on_expiry():
    """Verify node_down overrides a congestion fault on an attached link and recovers when node_down expires."""
    sim = Simulator(seed=42)

    # Congestion on core_1-dist_1 for 4 ticks
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=4)
    # node_down on dist_1 for 2 ticks
    sim.inject_fault("node_down", "dist_1", duration=2)

    # Tick 1: node is down, attached link must be down (overriding congestion)
    m1 = sim.tick()
    link1 = next(x for x in m1 if x["target_id"] == "core_1-dist_1")
    assert link1["status"] == "down"
    assert link1["loss_pct"] == 100.0
    assert link1["latency_ms"] == 0.0

    # Tick 2: still down
    m2 = sim.tick()
    link2 = next(x for x in m2 if x["target_id"] == "core_1-dist_1")
    assert link2["status"] == "down"
    assert link2["loss_pct"] == 100.0

    # Tick 3: node_down expired (duration=2 completed), congestion still active (tick 3 of 4)
    m3 = sim.tick()
    dist_node_3 = next(x for x in m3 if x["target_id"] == "dist_1")
    link3 = next(x for x in m3 if x["target_id"] == "core_1-dist_1")
    assert dist_node_3["status"] == "up"
    assert link3["status"] == "up"
    assert link3["latency_ms"] == pytest.approx(75.0, abs=10.0)  # ~5x 15ms baseline
    assert link3["loss_pct"] > 0.5

    # Tick 4: congestion tick 4 of 4
    m4 = sim.tick()
    link4 = next(x for x in m4 if x["target_id"] == "core_1-dist_1")
    assert link4["status"] == "up"
    assert link4["latency_ms"] > 60.0

    # Tick 5: congestion expired, fully restored to healthy baseline
    m5 = sim.tick()
    link5 = next(x for x in m5 if x["target_id"] == "core_1-dist_1")
    assert link5["status"] == "up"
    assert link5["latency_ms"] == pytest.approx(15.0, abs=2.0)
    assert link5["loss_pct"] < 0.5


def test_fault_clear_node_down():
    """Verify clear_fault restores node to status up and healthy loss."""
    sim = Simulator(seed=42)
    sim.inject_fault("node_down", "core_2")

    m1 = sim.tick()
    assert next(m for m in m1 if m["target_id"] == "core_2")["status"] == "down"

    sim.clear_fault("core_2")
    m2 = sim.tick()
    core2_m = next(m for m in m2 if m["target_id"] == "core_2")
    assert core2_m["status"] == "up"
    assert core2_m["loss_pct"] < 0.5


def test_fault_flapping():
    """Verify flapping fault alternates link status between up and down."""
    sim = Simulator(seed=42)

    sim.inject_fault("flapping", ("dist_1", "access_1"), duration=4)

    # Tick 1: step_count 1 (odd) -> down
    m1 = sim.tick()
    flap1 = next(m for m in m1 if m["target_id"] == "dist_1-access_1")
    assert flap1["status"] == "down"
    assert flap1["loss_pct"] == 100.0

    # Tick 2: step_count 2 (even) -> up
    m2 = sim.tick()
    flap2 = next(m for m in m2 if m["target_id"] == "dist_1-access_1")
    assert flap2["status"] == "up"
    assert flap2["loss_pct"] < 0.5
    assert flap2["latency_ms"] == pytest.approx(30.0, abs=3.0)

    # Tick 3: step_count 3 (odd) -> down
    m3 = sim.tick()
    flap3 = next(m for m in m3 if m["target_id"] == "dist_1-access_1")
    assert flap3["status"] == "down"
    assert flap3["loss_pct"] == 100.0

    # Tick 4: step_count 4 (even) -> up
    m4 = sim.tick()
    flap4 = next(m for m in m4 if m["target_id"] == "dist_1-access_1")
    assert flap4["status"] == "up"


def test_fault_duration_auto_expires():
    """Verify fault with duration expires automatically after specified ticks."""
    sim = Simulator(seed=42)

    # Inject fault for exactly 2 ticks
    sim.inject_fault("node_down", "cust_5", duration=2)

    # Tick 1: active
    m1 = sim.tick()
    assert next(m for m in m1 if m["target_id"] == "cust_5")["status"] == "down"

    # Tick 2: active
    m2 = sim.tick()
    assert next(m for m in m2 if m["target_id"] == "cust_5")["status"] == "down"

    # Tick 3: expired, normal healthy state restored
    m3 = sim.tick()
    cust5_m3 = next(m for m in m3 if m["target_id"] == "cust_5")
    assert cust5_m3["status"] == "up"
    assert cust5_m3["loss_pct"] < 0.5


def test_target_resolution_flexibility():
    """Verify inject_fault accepts tuple, reversed tuple, string, or canonical format."""
    sim = Simulator(seed=42)

    # Tuple
    sim.inject_fault("congestion", ("dist_2", "access_3"), duration=1)
    assert "dist_2-access_3" in sim.active_faults
    sim.clear_fault(("dist_2", "access_3"))

    # Reversed tuple
    sim.inject_fault("congestion", ("access_3", "dist_2"), duration=1)
    assert "dist_2-access_3" in sim.active_faults
    sim.clear_fault("access_3-dist_2")

    # String with separator
    sim.inject_fault("congestion", "dist_2--access_3", duration=1)
    assert "dist_2-access_3" in sim.active_faults
    sim.clear_fault("dist_2-access_3")


def test_clear_all_faults():
    """Verify clear_all_faults clears multiple faults across nodes and links."""
    sim = Simulator(seed=42)

    sim.inject_fault("congestion", ("core_1", "dist_1"))
    sim.inject_fault("node_down", "dist_2")
    sim.inject_fault("flapping", ("dist_3", "access_5"))
    assert len(sim.active_faults) == 3

    sim.clear_all_faults()
    assert len(sim.active_faults) == 0

    m = sim.tick()
    assert next(m for m in m if m["target_id"] == "core_1-dist_1")["latency_ms"] == pytest.approx(15.0, abs=2.0)
    assert next(m for m in m if m["target_id"] == "dist_2")["status"] == "up"
    assert next(m for m in m if m["target_id"] == "dist_3-access_5")["status"] == "up"


def test_invalid_fault_inputs_raise_errors():
    """Verify validation and error raising on invalid inputs."""
    sim = Simulator(seed=42)

    # Unknown fault kind
    with pytest.raises(ValueError, match="Unknown fault kind"):
        sim.inject_fault("alien_invasion", "core_1")

    # Unknown target
    with pytest.raises(ValueError, match="not found in topology"):
        sim.inject_fault("node_down", "mars_router")

    # node_down on link
    with pytest.raises(ValueError, match="can only be injected on a node"):
        sim.inject_fault("node_down", ("core_1", "core_2"))

    # congestion on node
    with pytest.raises(ValueError, match="can only be injected on a link"):
        sim.inject_fault("congestion", "core_1")

    # flapping on node
    with pytest.raises(ValueError, match="can only be injected on a link"):
        sim.inject_fault("flapping", "core_1")

    # non-positive duration
    with pytest.raises(ValueError, match="duration must be a positive integer"):
        sim.inject_fault("congestion", ("core_1", "dist_1"), duration=0)


def test_fault_does_not_shift_unrelated_target_jitter():
    """Verify drawing RNG jitter unconditionally prevents a fault from shifting noise of other targets."""
    base_time = "2026-11-18T00:00:00Z"
    sim_clean = Simulator(seed=42, base_time=base_time)
    sim_faulty = Simulator(seed=42, base_time=base_time)

    # Inject fault on dist_1 in sim_faulty only
    sim_faulty.inject_fault("node_down", "dist_1")

    m_clean = sim_clean.tick()
    m_faulty = sim_faulty.tick()

    # Compare an unrelated target: core_2 node and core_2-dist_3 link
    clean_node = next(x for x in m_clean if x["target_id"] == "core_2")
    faulty_node = next(x for x in m_faulty if x["target_id"] == "core_2")
    assert clean_node["latency_ms"] == faulty_node["latency_ms"]
    assert clean_node["loss_pct"] == faulty_node["loss_pct"]

    clean_link = next(x for x in m_clean if x["target_id"] == "core_2-dist_3")
    faulty_link = next(x for x in m_faulty if x["target_id"] == "core_2-dist_3")
    assert clean_link["latency_ms"] == faulty_link["latency_ms"]
    assert clean_link["loss_pct"] == faulty_link["loss_pct"]


def test_duration_strict_validation():
    """Verify duration must be an int, rejecting bool, float, NaN, and non-positive numbers."""
    sim = Simulator(seed=42)

    with pytest.raises(TypeError, match="duration must be an integer"):
        sim.inject_fault("congestion", ("core_1", "dist_1"), duration=True)

    with pytest.raises(TypeError, match="duration must be an integer"):
        sim.inject_fault("congestion", ("core_1", "dist_1"), duration=float("nan"))

    with pytest.raises(TypeError, match="duration must be an integer"):
        sim.inject_fault("congestion", ("core_1", "dist_1"), duration=2.5)

    with pytest.raises(ValueError, match="duration must be a positive integer"):
        sim.inject_fault("congestion", ("core_1", "dist_1"), duration=0)

    with pytest.raises(ValueError, match="duration must be a positive integer"):
        sim.inject_fault("congestion", ("core_1", "dist_1"), duration=-5)


def test_clear_fault_unhashable_target_returns_false():
    """Verify clear_fault returns False without raising TypeError for unhashable targets."""
    sim = Simulator(seed=42)
    assert sim.clear_fault(["core_1", "dist_1"]) is False
    assert sim.clear_fault({"invalid": "target"}) is False

