"""Interactive NetworkX topology visualization for the NetPulse dashboard."""

import re
from typing import Any, Dict, Optional, Tuple

import networkx as nx
import plotly.graph_objects as go


HEALTH_COLORS = {
    "HEALTHY": "#28a745",
    "WARNING": "#f0ad4e",
    "CRITICAL": "#dc3545",
    "UNKNOWN": "#adb5bd",
}

TIER_COLORS = {
    "core": "#007bff",
    "distribution": "#20c997",
    "access": "#fd7e14",
    "customer": "#adb5bd",
}

def canonical_link_id(u: str, v: str) -> str:
    """Return the simulator-style canonical link identifier."""
    return f"{u}-{v}"


def get_link_status(
    u: str,
    v: str,
    targets: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Return monitoring state for an edge, checking both link ID orientations."""
    direct = targets.get(canonical_link_id(u, v))
    if direct is not None:
        return direct
    return targets.get(canonical_link_id(v, u), {})


def natural_sort_key(node_id: str) -> Tuple[Tuple[int, Any], ...]:
    """Sort names containing numbers naturally, such as cust_2 before cust_10."""
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.lower())
        for part in re.split(r"(\d+)", node_id)
        if part
    )


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
            (
                node_id
                for node_id, attrs in graph.nodes(data=True)
                if attrs.get("type") == tier
            ),
            key=natural_sort_key,
        )
        if not nodes:
            continue
        span = max(1, len(nodes) - 1)
        for index, node_id in enumerate(nodes):
            x = -0.5 * span + index
            positions[node_id] = (x, tier_y[tier])
    return positions


def count_layout_edge_crossings(
    graph: nx.Graph,
    positions: Dict[str, Tuple[float, float]],
) -> int:
    """Count proper intersections between distinct topology edge segments."""
    edges = list(graph.edges())
    crossings = 0

    def orientation(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def on_segment(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> bool:
        return (
            min(a[0], c[0]) <= b[0] <= max(a[0], c[0])
            and min(a[1], c[1]) <= b[1] <= max(a[1], c[1])
        )

    def proper_intersection(
        a: Tuple[float, float],
        b: Tuple[float, float],
        c: Tuple[float, float],
        d: Tuple[float, float],
    ) -> bool:
        o1 = orientation(a, b, c)
        o2 = orientation(a, b, d)
        o3 = orientation(c, d, a)
        o4 = orientation(c, d, b)
        eps = 1e-9
        if o1 * o2 < -eps and o3 * o4 < -eps:
            return True
        if abs(o1) <= eps and on_segment(a, c, b):
            return True
        if abs(o2) <= eps and on_segment(a, d, b):
            return True
        if abs(o3) <= eps and on_segment(c, a, d):
            return True
        if abs(o4) <= eps and on_segment(c, b, d):
            return True
        return False

    for index, (u, v) in enumerate(edges):
        for u2, v2 in edges[index + 1:]:
            if set((u, v)) & set((u2, v2)):
                continue
            if proper_intersection(positions[u], positions[v], positions[u2], positions[v2]):
                crossings += 1
    return crossings


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
        state = get_link_status(u, v, targets)
        has_data = bool(state)
        status = str(state.get("status", "N/A")) if has_data else "N/A"
        health = str(state.get("health", "UNKNOWN")).upper() if has_data else "UNKNOWN"
        latency = state.get("current_latency_ms")
        loss = state.get("current_loss_pct")

        if status == "down" or health == "CRITICAL":
            color = HEALTH_COLORS["CRITICAL"]
        elif health == "WARNING":
            color = HEALTH_COLORS["WARNING"]
        elif health == "HEALTHY":
            color = HEALTH_COLORS["HEALTHY"]
        else:
            color = HEALTH_COLORS["UNKNOWN"]

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
                    f"Latency: {latency if latency is not None else 'N/A'}"
                    f"{' ms' if latency is not None else ''}<br>"
                    f"Packet loss: {loss if loss is not None else 'N/A'}"
                    f"{'%' if loss is not None else ''}"
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

    for node_id in sorted(graph.nodes(), key=natural_sort_key):
        data = graph.nodes[node_id]
        state = targets.get(node_id)
        if state is None:
            health = "UNKNOWN"
            status = "N/A"
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
        node_colors.append(TIER_COLORS.get(str(data.get("type", "")).lower(), "#adb5bd"))
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

    fig.update_layout(
        title=None,
        showlegend=False,
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
