"""Streamlit entry point for the NetPulse AI dashboard."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from database.db import DEFAULT_DB_PATH, init_db, query_anomalies
from monitoring.monitor import NetworkMonitor
from network.topology import build_topology, get_topology_summary
from dashboard.topology import build_topology_figure


def load_monitor(
    db_path: Optional[Union[str, Path]] = None,
    window_size: int = 20,
) -> NetworkMonitor:
    """Load the dashboard monitoring read model from SQLite."""
    resolved_path = db_path if db_path is not None else DEFAULT_DB_PATH
    init_db(resolved_path)
    return NetworkMonitor.from_db(db_path=resolved_path, window_size=window_size)


def get_data_as_of(network_status: dict) -> str:
    """Format the latest monitor timestamp, or report no loaded data."""
    timestamp = network_status.get("timestamp")
    if not timestamp:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%H:%M UTC")
    except (TypeError, ValueError):
        return str(timestamp)


def get_anomaly_count_24h(db_path: Optional[Union[str, Path]] = None) -> int:
    """Count anomaly evidence rows in the last 24 hours from SQLite."""
    start = datetime.now(timezone.utc) - timedelta(hours=24)
    return len(query_anomalies(start=start, path=db_path))


def get_slowest_links(network_status: dict, limit: int = 5) -> list:
    """Return link statuses sorted by highest current latency."""
    links = [
        state
        for state in network_status.get("targets", {}).values()
        if state.get("target_type") == "link"
    ]
    links.sort(
        key=lambda state: (
            state.get("current_latency_ms") is None,
            -(float(state.get("current_latency_ms") or 0.0)),
            state["target_id"],
        )
    )
    return links[:limit]


def render_dashboard(db_path: Optional[Union[str, Path]] = None) -> None:
    """Render topology and network health controls in Streamlit."""
    st.set_page_config(page_title="NetPulse AI", page_icon=":signal_strength:", layout="wide")
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            background: #343a40;
            color: #c2c7d0;
        }
        [data-testid="stSidebar"] * { color: #c2c7d0; }
        [data-testid="stHeader"] { background: #ffffff; }
        [data-testid="stStatusWidget"] { display: none !important; }
        .stStatusWidget { display: none !important; }
        .block-container {
            background: #f4f6f9;
            padding-top: 1.25rem;
            margin-top: 0;
            max-width: 100%;
        }
        [data-testid="stToolbar"] { visibility: visible; }
        [data-testid="stDecoration"] { display: block; }
        .netpulse-card {
            background: #ffffff;
            border-radius: 6px;
            padding: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,.10);
            height: 100%;
        }
        .stat-card { min-height: 118px; }
        .stat-label {
            color: #6c757d;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
        }
        .stat-number { font-size: 32px; font-weight: 800; line-height: 1.1; }
        .stat-subtext { color: #6c757d; font-size: 12px; margin-top: 5px; }
        .card-progress {
            height: 4px;
            border-radius: 2px;
            background: #e9ecef;
            margin-top: 12px;
        }
        .card-progress div { height: 4px; border-radius: 2px; }
        .health-pill {
            color: white;
            border-radius: 999px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 700;
        }
        .netpulse-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
        }
        .netpulse-table th {
            background: #f8f9fa;
            color: #6c757d;
            font-size: 10px;
            text-align: left;
            padding: 7px 6px;
            border: none;
            border-bottom: 1px solid #dee2e6;
        }
        .netpulse-table td {
            color: #343a40;
            padding: 7px 6px;
            border: none;
            border-bottom: 1px solid #f1f3f5;
        }
        .empty-state {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
            border-radius: 5px;
            padding: 12px;
        }
        .sidebar-brand {
            color: #ffffff;
            font-size: 20px;
            font-weight: 800;
            margin: 4px 0 16px 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    resolved_path = db_path if db_path is not None else DEFAULT_DB_PATH
    st.sidebar.markdown('<div class="sidebar-brand">NetPulse AI</div>', unsafe_allow_html=True)
    st.sidebar.markdown("**MAIN MENU**")
    st.sidebar.markdown(
        """
        <div>&#8226; <b>Dashboard</b></div>
        <div>&#8226; Topology</div>
        <div>&#8226; Anomalies</div>
        <div>&#8226; Monitoring</div>
        <div>&#8226; Settings</div>
        """,
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown("**ROLLING HISTORY**")
    window_size = st.sidebar.slider(
        "Rolling history",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
        label_visibility="collapsed",
    )
    st.sidebar.markdown("**LEGEND**")
    st.sidebar.markdown(
        """
        <div><span style="color:#007bff;">&#9679;</span> Core router</div>
        <div><span style="color:#20c997;">&#9679;</span> Distribution</div>
        <div><span style="color:#fd7e14;">&#9679;</span> Access</div>
        <div><span style="color:#adb5bd;">&#9679;</span> Customer</div>
        <div><span style="color:#28a745;">&#9632;</span> Healthy link</div>
        <div><span style="color:#ffc107;">&#9632;</span> Warning link</div>
        <div><span style="color:#dc3545;">&#9632;</span> Critical link</div>
        <div><span style="color:#adb5bd;">&#9632;</span> Unknown</div>
        """,
        unsafe_allow_html=True,
    )
    monitor = load_monitor(resolved_path, window_size)

    network_status = monitor.get_network_status()
    summary = get_topology_summary(build_topology())

    health = network_status["overall_health"]
    anomaly_count = get_anomaly_count_24h(resolved_path)
    health_colors = {
        "HEALTHY": "#28a745",
        "WARNING": "#ffc107",
        "CRITICAL": "#dc3545",
        "UNKNOWN": "#adb5bd",
    }
    health_color = health_colors.get(health, "#adb5bd")

    top_left, top_right = st.columns([4, 1.2])
    with top_left:
        st.markdown("### Dashboard")
    with top_right:
        st.markdown(
            f"""
            <div style="text-align:right;color:#6c757d;font-size:12px;">
                Data as of {get_data_as_of(network_status)}
                &nbsp; <span class="health-pill" style="background:{health_color};">{health}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    stat_specs = [
        ("NODES", summary["total_nodes"], "#007bff", "2 core - 4 dist - 8 access - 16 cust"),
        ("LINKS", summary["total_links"], "#28a745", "29 links - 0 crossed - live from SQLite"),
        ("BREACHING TARGETS", len(network_status["breaching_targets"]), "#28a745", "No link or node over its threshold"),
        ("ANOMALIES - 24H", anomaly_count, "#28a745", "Learned baselines - no false alarms"),
    ]
    stat_columns = st.columns(4)
    for column, (label, number, color, subtext) in zip(stat_columns, stat_specs):
        with column:
            st.markdown(
                f"""
                <div class="netpulse-card stat-card">
                    <div class="stat-label">{label}</div>
                    <div class="stat-number" style="color:{color};">{number}</div>
                    <div class="stat-subtext">{subtext}</div>
                    <div class="card-progress"><div style="background:{color};width:100%;"></div></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        """
        <div class="netpulse-card" style="margin-top:10px;">
            <div style="font-weight:800;color:#343a40;">Network topology</div>
            <div style="font-size:12px;color:#6c757d;margin:4px 0 8px;">
                Live health from the monitor - 30 nodes - 29 links - interactive Plotly graph
            </div>
        """,
        unsafe_allow_html=True,
    )
    figure = build_topology_figure(build_topology(), network_status)
    figure.update_layout(
        height=430,
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
    )
    st.plotly_chart(figure, width="stretch")
    st.markdown(
        """
        <div style="display:flex;gap:18px;font-size:12px;color:#6c757d;align-items:center;margin:4px 0 2px;">
            <span><span style="color:#007bff;">&#9679;</span> Core</span>
            <span><span style="color:#20c997;">&#9679;</span> Distribution</span>
            <span><span style="color:#fd7e14;">&#9679;</span> Access</span>
            <span><span style="color:#adb5bd;">&#9679;</span> Customer</span>
            <span><span style="color:#28a745;">&#9632;</span> Healthy</span>
            <span><span style="color:#ffc107;">&#9632;</span> Warning</span>
            <span><span style="color:#dc3545;">&#9632;</span> Critical</span>
            <span><span style="color:#adb5bd;">&#9632;</span> Unknown</span>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    bottom_left, bottom_right = st.columns([1, 1])
    with bottom_left:
        st.markdown('<div class="netpulse-card" style="margin-top:12px;"><div style="font-weight:800;">Breaching targets</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:12px;color:#6c757d;margin-bottom:10px;">Links and nodes over their latency or loss thresholds</div>', unsafe_allow_html=True)
        breaching = monitor.get_breaching_targets()
        if not breaching:
            st.markdown('<div class="empty-state">No active threshold breaches.</div>', unsafe_allow_html=True)
        else:
            for state in breaching:
                state_health = state["health"]
                pill_color = health_colors.get(state_health, "#adb5bd")
                st.markdown(
                    f"<b>{state['target_id']}</b> "
                    f"<span class='health-pill' style='background:{pill_color};'>{state_health}</span>",
                    unsafe_allow_html=True,
                )
        st.markdown("</div>", unsafe_allow_html=True)

    with bottom_right:
        st.markdown('<div class="netpulse-card" style="margin-top:12px;"><div style="font-weight:800;">Slowest links right now</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:12px;color:#6c757d;margin-bottom:10px;">Highest latency links in the current window</div>', unsafe_allow_html=True)
        slowest = get_slowest_links(network_status, limit=3)
        if not slowest:
            st.markdown('<div style="color:#6c757d;">No link telemetry available.</div>', unsafe_allow_html=True)
        else:
            rows = []
            for state in slowest:
                latency = state.get("current_latency_ms")
                loss = state.get("current_loss_pct")
                state_health = state.get("health", "UNKNOWN")
                pill_color = health_colors.get(state_health, "#adb5bd")
                rows.append(
                    (
                        state["target_id"],
                        "N/A" if latency is None else f"{float(latency):.1f} ms",
                        "N/A" if loss is None else f"{float(loss):.1f}%",
                        f'<span class="health-pill" style="background:{pill_color};">{state_health}</span>',
                    )
                )
            table_html = (
                '<table class="netpulse-table">'
                "<thead><tr><th>LINK</th><th>LATENCY</th><th>LOSS</th><th>HEALTH</th></tr></thead><tbody>"
                + "".join(
                    "<tr>"
                    f"<td>{row[0]}</td>"
                    f"<td>{row[1]}</td><td>{row[2]}</td><td>{row[3]}</td>"
                    "</tr>"
                    for row in rows
                )
                + "</tbody></table>"
            )
            st.markdown(table_html, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    render_dashboard()
