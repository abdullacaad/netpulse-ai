"""Streamlit entry point for the NetPulse AI dashboard."""

import sys
from pathlib import Path
from typing import Optional, Union

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import streamlit as st

from database.db import DEFAULT_DB_PATH, init_db
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


def render_dashboard(db_path: Optional[Union[str, Path]] = None) -> None:
    """Render topology and network health controls in Streamlit."""
    st.set_page_config(page_title="NetPulse AI", page_icon="📡", layout="wide")
    st.title("NetPulse AI")
    st.caption("Simulated network topology and current SQLite monitoring state")

    resolved_path = db_path if db_path is not None else DEFAULT_DB_PATH
    window_size = st.sidebar.slider(
        "Rolling history",
        min_value=5,
        max_value=50,
        value=20,
        step=5,
    )
    monitor = load_monitor(resolved_path, window_size)

    network_status = monitor.get_network_status()
    summary = get_topology_summary(build_topology())

    health = network_status["overall_health"]
    health_color = {
        "HEALTHY": "green",
        "WARNING": "orange",
        "CRITICAL": "red",
        "UNKNOWN": "gray",
    }.get(health, "gray")
    st.markdown(f"**Network health:** :{health_color}[{health}]")

    columns = st.columns(4)
    columns[0].metric("Nodes", summary["total_nodes"])
    columns[1].metric("Links", summary["total_links"])
    columns[2].metric("Breaching targets", len(network_status["breaching_targets"]))
    columns[3].metric("Active breaches", len(network_status["active_breaches"]))

    figure = build_topology_figure(build_topology(), network_status)
    st.plotly_chart(figure, width="stretch")

    with st.expander("Breaching targets"):
        breaching = monitor.get_breaching_targets()
        if not breaching:
            st.success("No active threshold breaches.")
        else:
            for state in breaching:
                st.write(
                    f"**{state['target_id']}** — {state['health']} "
                    f"(latency: {state['current_latency_ms']} ms, "
                    f"loss: {state['current_loss_pct']}%)"
                )


if __name__ == "__main__":
    render_dashboard()
