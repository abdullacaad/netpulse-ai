"""Tests for NetworkX topology visualization and dashboard monitoring state."""

from pathlib import Path
import inspect
import sys

import networkx as nx
import pytest

from dashboard.app import load_monitor
from dashboard.topology import (
    HEALTH_COLORS,
    build_topology_figure,
    build_topology_positions,
    canonical_link_id,
    count_layout_edge_crossings,
    get_link_status,
    natural_sort_key,
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
    link_state = get_link_status("core_1", "dist_1", status["targets"])
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


def test_repo_bootstrap_and_read_only_app_source():
    """Verify app.py bootstraps the repo root and contains no live collector access."""
    app_source = Path(__file__).parents[1].joinpath("dashboard", "app.py").read_text()
    assert "sys.path.insert" in app_source
    assert "monitoring.collector" not in app_source
    assert "network.simulator" not in app_source
    assert "Collect live sample" not in app_source
    assert 'st.plotly_chart(figure, width="stretch")' in app_source


def test_natural_customer_order_and_zero_crossings():
    """Verify numbered customer names sort naturally and edge crossings disappear."""
    graph = build_topology()
    positions = build_topology_positions(graph)
    customer_ids = [
        node_id
        for node_id in positions
        if node_id.startswith("cust_")
    ]

    assert customer_ids == sorted(customer_ids, key=natural_sort_key)
    assert customer_ids.index("cust_2") < customer_ids.index("cust_10")
    assert count_layout_edge_crossings(graph, positions) == 0


def test_empty_database_renders_unknown_no_data():
    """Verify empty monitoring state uses UNKNOWN rather than HEALTHY or static baselines."""
    monitor = NetworkMonitor()
    network_status = monitor.get_network_status()
    assert network_status["overall_health"] == "UNKNOWN"

    figure = build_topology_figure(build_topology(), network_status)
    node_trace = next(
        trace for trace in figure.data if getattr(trace, "mode", "") == "markers+text"
    )
    cust_index = list(node_trace.text).index("cust_1")
    assert node_trace.marker.color[cust_index] == HEALTH_COLORS["UNKNOWN"]
    assert "Status: N/A" in node_trace.hovertext[cust_index]

    line_traces = [
        trace for trace in figure.data if getattr(trace, "mode", "") == "lines"
    ]
    for trace in line_traces:
        assert trace.line.color == HEALTH_COLORS["UNKNOWN"]
        assert "Latency: N/A" in trace.hovertemplate
        assert "Packet loss: N/A" in trace.hovertemplate


def test_slider_window_is_reloaded_on_each_dashboard_render(tmp_path: Path):
    """Verify changing the window argument immediately reloads bounded SQLite history."""
    db_path = tmp_path / "slider.db"
    rows = [
        {
            "timestamp": f"2026-11-18T12:00:{i:02d}Z",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": float(i),
            "loss_pct": 0.1,
            "status": "up",
        }
        for i in range(6)
    ]
    from database.db import insert_measurements
    insert_measurements(rows, db_path)

    short_monitor = load_monitor(db_path=db_path, window_size=5)
    long_monitor = load_monitor(db_path=db_path, window_size=6)
    assert len(short_monitor.get_target_status("core_1-dist_1")["recent_history"]) == 5
    assert len(long_monitor.get_target_status("core_1-dist_1")["recent_history"]) == 6

    app_source = Path(__file__).parents[1].joinpath("dashboard", "app.py").read_text()
    assert "monitor = load_monitor(resolved_path, window_size)" in app_source


def test_unused_tier_constant_and_link_status_signature_removed():
    """Verify the tier constant is gone and get_link_status has no graph parameter."""
    import dashboard.topology as topology_module

    assert not hasattr(topology_module, "TIER_COLORS")
    parameters = list(inspect.signature(topology_module.get_link_status).parameters)
    assert parameters == ["u", "v", "targets"]
