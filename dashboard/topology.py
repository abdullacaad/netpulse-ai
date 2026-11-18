"""Interactive NetworkX topology visualization for the NetPulse dashboard."""

from typing import Any, Dict, Iterable, Optional, Tuple

import networkx as nx
import plotly.graph_objects as go


HEALTH_COLORS = {
    "HEALTHY": "#28a745",
    "WARNING": "#f0ad4e",
    "CRITICAL": "#dc3545",
    "UNKNOWN": "#adb5bd",
}

TIER_COLORS = {
    "core": "#2563eb",
    "distribution": "#7c3aed",
    "access": "#0891b2",
    "customer": "#64748b",
}


def canonical_link_id(u: str, v: str) -> str:
    """Return the simulator-style canonical link identifier."""
    return f"{u}-{v}"


def get_link_status(
    graph: nx.Graph,
    u: str,
    v: str,
    targets: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Return monitoring state for an edge, checking both link ID orientations."""
    direct = targets.get(canonical_link_id(u, v))
    if direct is not None:
        return direct
    return targets.get(canonical_link_id(v, u), {})


def build_topology_positions(graph: nx.Graph) -> Dict[str, Tuple[float, float]]:
    """Create a deterministic hierarchical layout for the ISP topology."""
    tier_y = {
        "core": 3.0,
        "distribution": 2.0,
        "access": 1.0,
        "customer": 0.0,
    }
    positions: Dict[str, Tuple[float, float]] = {}
    for tier in ("core", "distribution", "access", "customer"):
        nodes = sorted(
            node_id
            for node_id, attrs in graph.nodes(data=True)
            if attrs.get("type") == tier
        )
        if not nodes:
            continue
        span = max(1, len(nodes) - 1)
        for index, node_id in enumerate(nodes):
            x = -0.5 * span + index
            positions[node_id] = (x, tier_y[tier])
    return positions


def build_topology_figure(
    graph: nx.Graph,
    network_status: Optional[Dict[str, Any]] = None,
) -> go.Figure:
    """Build an interactive Plotly graph colored by current NetworkMonitor state."""
    network_status = network_status or {}
    targets = network_status.get("targets", {})
    positions = build_topology_positions(graph)
    fig = go.Figure()

    # Edge traces are added first so nodes render above links.
    for u, v, data in graph.edges(data=True):
        state = get_link_status(graph, u, v, targets)
        status = str(state.get("status", data.get("status", "up"))).lower()
        health = str(state.get("health", "HEALTHY")).upper()
        latency = state.get("current_latency_ms")
        loss = state.get("current_loss_pct")
        if latency is None:
            latency = data.get("latency_ms")
        if loss is None:
            loss = data.get("loss_pct")

        if status == "down" or health == "CRITICAL":
            color = HEALTH_COLORS["CRITICAL"]
        elif health == "WARNING":
            color = HEALTH_COLORS["WARNING"]
        else:
            color = HEALTH_COLORS["HEALTHY"]

        try:
            loss_width = 2.0 + min(float(loss or 0.0), 10.0) * 0.25
        except (TypeError, ValueError):
            loss_width = 2.0

        x0, y0 = positions[u]
        x1, y1 = positions[v]
        fig.add_trace(
            go.Scatter(
                x=[x0, x1, None],
                y=[y0, y1, None],
                mode="lines",
                line={"width": loss_width, "color": color},
                hovertemplate=(
                    f"<b>{u}-{v}</b><br>"
                    f"Status: {status}<br>"
                    f"Health: {health}<br>"
                    f"Latency: {latency} ms<br>"
                    f"Packet loss: {loss}%"
                    "<extra></extra>"
                ),
                showlegend=False,
            )
        )

    node_x: list[float] = []
    node_y: list[float] = []
    node_text: list[str] = []
    node_hover: list[str] = []
    node_colors: list[str] = []
    node_sizes: list[int] = []

    for node_id in sorted(graph.nodes()):
        data = graph.nodes[node_id]
        state = targets.get(node_id)
        if state is None:
            health = "UNKNOWN"
            status = str(data.get("status", "up"))
            latency = None
            loss = None
        else:
            health = str(state.get("health", "UNKNOWN")).upper()
            status = str(state.get("status", data.get("status", "up")))
            latency = state.get("current_latency_ms")
            loss = state.get("current_loss_pct")

        x, y = positions[node_id]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node_id)
        node_colors.append(HEALTH_COLORS.get(health, HEALTH_COLORS["UNKNOWN"]))
        node_sizes.append(30 if data.get("type") == "core" else 23)
        node_hover.append(
            f"<b>{node_id}</b><br>"
            f"Type: {data.get('type', 'unknown')}<br>"
            f"Status: {status}<br>"
            f"Health: {health}<br>"
            f"Latency: {latency if latency is not None else 'N/A'} ms<br>"
            f"Packet loss: {loss if loss is not None else 'N/A'}%"
        )

    fig.add_trace(
        go.Scatter(
            x=node_x,
            y=node_y,
            mode="markers+text",
            text=node_text,
            textposition="top center",
            textfont={"size": 9, "color": "#111827"},
            marker={
                "size": node_sizes,
                "color": node_colors,
                "line": {"width": 2, "color": "#ffffff"},
            },
            hovertemplate="%{hovertext}<extra></extra>",
            hovertext=node_hover,
            showlegend=False,
        )
    )

    for health, color in (
        ("Healthy", HEALTH_COLORS["HEALTHY"]),
        ("Warning", HEALTH_COLORS["WARNING"]),
        ("Critical", HEALTH_COLORS["CRITICAL"]),
        ("Unknown", HEALTH_COLORS["UNKNOWN"]),
    ):
        fig.add_trace(
            go.Scatter(
                x=[None],
                y=[None],
                mode="markers",
                marker={"size": 12, "color": color},
                name=health,
            )
        )

    fig.update_layout(
        title="NetPulse AI - Network Topology",
        showlegend=True,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        hovermode="closest",
        dragmode="pan",
        plot_bgcolor="#f8fafc",
        paper_bgcolor="#ffffff",
        margin={"l": 20, "r": 20, "t": 80, "b": 20},
        xaxis={"visible": False, "range": [-9, 9]},
        yaxis={"visible": False, "range": [-0.5, 3.5]},
        height=650,
    )
    return fig
