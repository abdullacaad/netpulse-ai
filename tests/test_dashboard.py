"""Tests for NetworkX topology visualization and dashboard monitoring state."""

from pathlib import Path

import networkx as nx
import pytest

from dashboard.app import load_monitor
from dashboard.topology import (
    HEALTH_COLORS,
    build_topology_figure,
    build_topology_positions,
    canonical_link_id,
    get_link_status,
)
from monitoring.monitor import NetworkMonitor
from network.topology import build_topology, get_topology_summary


def test_topology_visualization_contains_full_simulated_graph():
    """Verify the visualization includes all 30 nodes and 29 links."""
    graph = build_topology()
    figure = build_topology_figure(graph)

    summary = get_topology_summary(graph)
    assert summary["total_nodes"] == 30
    assert summary["total_links"] == 29

    node_trace = next(
        trace for trace in figure.data if getattr(trace, "mode", "") == "markers+text"
    )
    assert len(node_trace.x) == 30
    assert len(node_trace.text) == 30

    line_traces = [
        trace
        for trace in figure.data
        if getattr(trace, "mode", "") == "lines"
    ]
    assert len(line_traces) == 29


def test_topology_layout_is_deterministic_and_hierarchical():
    """Verify every node receives a stable tier-based position."""
    graph = build_topology()
    positions = build_topology_positions(graph)

    assert positions == build_topology_positions(graph)
    assert set(positions) == set(graph.nodes)
    assert positions["core_1"][1] == 3.0
    assert positions["dist_1"][1] == 2.0
    assert positions["access_1"][1] == 1.0
    assert positions["cust_1"][1] == 0.0


def test_node_colors_reflect_network_monitor_health():
    """Verify node marker colors come from live NetworkMonitor health."""
    monitor = NetworkMonitor()
    for target_id, health, latency, loss, status in (
        ("dist_1", "healthy", 1.0, 0.0, "up"),
        ("dist_2", "warning", 1.0, 3.0, "up"),
        ("dist_3", "critical", 0.0, 100.0, "down"),
    ):
        monitor.record_measurement(
            {
                "timestamp": "2026-11-18T12:00:00Z",
                "target_type": "node",
                "target_id": target_id,
                "latency_ms": latency,
                "loss_pct": loss,
                "status": status,
            }
        )

    figure = build_topology_figure(build_topology(), monitor.get_network_status())
    node_trace = next(
        trace for trace in figure.data if getattr(trace, "mode", "") == "markers+text"
    )
    colors_by_node = dict(zip(node_trace.text, node_trace.marker.color))

    assert colors_by_node["dist_1"] == HEALTH_COLORS["HEALTHY"]
    assert colors_by_node["dist_2"] == HEALTH_COLORS["WARNING"]
    assert colors_by_node["dist_3"] == HEALTH_COLORS["CRITICAL"]
    assert colors_by_node["cust_1"] == HEALTH_COLORS["UNKNOWN"]


def test_link_colors_reflect_latency_and_packet_loss_state():
    """Verify link traces use critical/warning/healthy monitoring colors."""
    monitor = NetworkMonitor()
    monitor.record_measurement(
        {
            "timestamp": "2026-11-18T12:00:00Z",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": 75.0,
            "loss_pct": 1.0,
            "status": "up",
        }
    )
    monitor.record_measurement(
        {
            "timestamp": "2026-11-18T12:00:00Z",
            "target_type": "link",
            "target_id": "dist_1-access_1",
            "latency_ms": 30.0,
            "loss_pct": 3.0,
            "status": "up",
        }
    )
    monitor.record_measurement(
        {
            "timestamp": "2026-11-18T12:00:00Z",
            "target_type": "link",
            "target_id": "core_1-core_2",
            "latency_ms": 5.0,
            "loss_pct": 0.1,
            "status": "up",
        }
    )

    figure = build_topology_figure(build_topology(), monitor.get_network_status())
    line_traces = [
        trace
        for trace in figure.data
        if getattr(trace, "mode", "") == "lines"
    ]
    colors_by_link = {}
    for u, v in build_topology().edges:
        link_id = canonical_link_id(u, v)
        reverse_id = canonical_link_id(v, u)
        matching = next(
            trace
            for trace in line_traces
            if f"<b>{link_id}</b>" in trace.hovertemplate
            or f"<b>{reverse_id}</b>" in trace.hovertemplate
        )
        colors_by_link[link_id] = matching.line.color

    assert colors_by_link["core_1-dist_1"] == HEALTH_COLORS["CRITICAL"]
    assert colors_by_link["dist_1-access_1"] == HEALTH_COLORS["WARNING"]
    assert colors_by_link["core_1-core_2"] == HEALTH_COLORS["HEALTHY"]


def test_down_target_and_link_are_critical():
    """Verify down nodes and attached links use the critical color."""
    monitor = NetworkMonitor()
    monitor.record_measurement(
        {
            "timestamp": "2026-11-18T12:00:00Z",
            "target_type": "node",
            "target_id": "dist_1",
            "latency_ms": 0.0,
            "loss_pct": 100.0,
            "status": "down",
        }
    )
    monitor.record_measurement(
        {
            "timestamp": "2026-11-18T12:00:00Z",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": 0.0,
            "loss_pct": 100.0,
            "status": "down",
        }
    )

    status = monitor.get_network_status()
    figure = build_topology_figure(build_topology(), status)
    node_trace = next(
        trace for trace in figure.data if getattr(trace, "mode", "") == "markers+text"
    )
    colors_by_node = dict(zip(node_trace.text, node_trace.marker.color))
    assert colors_by_node["dist_1"] == HEALTH_COLORS["CRITICAL"]

    graph = build_topology()
    link_state = get_link_status(graph, "core_1", "dist_1", status["targets"])
    assert link_state["health"] == "CRITICAL"
    assert link_state["status"] == "down"


def test_load_monitor_populates_status_from_sqlite(tmp_path: Path):
    """Verify the dashboard read-model helper loads bounded SQLite history."""
    db_path = tmp_path / "dashboard.db"
    monitor = load_monitor(db_path=db_path, window_size=5)
    assert monitor.get_network_status()["total_targets"] == 0

    from database.db import insert_measurements

    insert_measurements(
        [
            {
                "timestamp": "2026-11-18T12:00:00Z",
                "target_type": "link",
                "target_id": "core_1-dist_1",
                "latency_ms": 75.0,
                "loss_pct": 1.0,
                "status": "up",
            }
        ],
        db_path,
    )
    loaded = load_monitor(db_path=db_path, window_size=5)
    status = loaded.get_target_status("core_1-dist_1")
    assert status["health"] == "CRITICAL"
    assert status["current_latency_ms"] == 75.0
