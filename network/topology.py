"""Synthetic ISP network topology generator for NetPulse AI.

Builds a NetworkX graph representing a hierarchical ISP infrastructure:
- 2 Core routers
- 4 Distribution nodes
- 8 Access nodes / 8 Access links
- 16 Customer endpoints
"""

from typing import Any, Dict, List, Tuple
import networkx as nx


def build_topology() -> nx.Graph:
    """Build and return the synthetic ISP network graph.

    Nodes:
      - 2 core routers (core_1, core_2)
      - 4 distribution nodes (dist_1 to dist_4)
      - 8 access nodes (access_1 to access_8)
      - 16 customer endpoints (cust_1 to cust_16)

    Node attributes:
      - type: 'core' | 'distribution' | 'access' | 'customer'
      - name: str identifier
      - status: 'up' | 'down' (default: 'up')

    Edge attributes:
      - latency_ms: float baseline latency (core ~5ms, dist ~15ms, access/customer ~30ms)
      - loss_pct: float baseline packet loss (healthy < 0.5%)
      - capacity_mbps: int link bandwidth
      - link_type: 'core' | 'distribution' | 'access' | 'customer'
      - status: 'up' | 'down' (default: 'up')
    """
    g = nx.Graph()

    # 1. Add Core Routers (2 nodes)
    for i in range(1, 3):
        node_id = f"core_{i}"
        g.add_node(node_id, type="core", name=node_id, status="up")

    # 2. Add Distribution Nodes (4 nodes)
    for i in range(1, 5):
        node_id = f"dist_{i}"
        g.add_node(node_id, type="distribution", name=node_id, status="up")

    # 3. Add Access Nodes (8 nodes)
    for i in range(1, 9):
        node_id = f"access_{i}"
        g.add_node(node_id, type="access", name=node_id, status="up")

    # 4. Add Customer Endpoints (16 nodes)
    for i in range(1, 17):
        node_id = f"cust_{i}"
        g.add_node(node_id, type="customer", name=node_id, status="up")

    # 5. Core-to-Core link (1 link, ~5 ms)
    g.add_edge(
        "core_1",
        "core_2",
        latency_ms=5.0,
        loss_pct=0.0,
        capacity_mbps=10000,
        link_type="core",
        status="up",
    )

    # 6. Core-to-Distribution links (4 links, ~15 ms)
    # core_1 connects to dist_1 and dist_2
    # core_2 connects to dist_3 and dist_4
    core_dist_mapping = {
        "core_1": ["dist_1", "dist_2"],
        "core_2": ["dist_3", "dist_4"],
    }
    for core, dist_nodes in core_dist_mapping.items():
        for dist in dist_nodes:
            g.add_edge(
                core,
                dist,
                latency_ms=15.0,
                loss_pct=0.0,
                capacity_mbps=1000,
                link_type="distribution",
                status="up",
            )

    # 7. Distribution-to-Access links (8 links, ~30 ms)
    # dist_1 connects to access_1, access_2
    # dist_2 connects to access_3, access_4
    # dist_3 connects to access_5, access_6
    # dist_4 connects to access_7, access_8
    for d_idx in range(1, 5):
        dist_node = f"dist_{d_idx}"
        acc_1 = f"access_{2 * d_idx - 1}"
        acc_2 = f"access_{2 * d_idx}"
        for acc in (acc_1, acc_2):
            g.add_edge(
                dist_node,
                acc,
                latency_ms=30.0,
                loss_pct=0.0,
                capacity_mbps=100,
                link_type="access",
                status="up",
            )

    # 8. Access-to-Customer links (16 links, ~30 ms)
    # Each access node connects to 2 customer endpoints
    for a_idx in range(1, 9):
        access_node = f"access_{a_idx}"
        cust_1 = f"cust_{2 * a_idx - 1}"
        cust_2 = f"cust_{2 * a_idx}"
        for cust in (cust_1, cust_2):
            g.add_edge(
                access_node,
                cust,
                latency_ms=30.0,
                loss_pct=0.0,
                capacity_mbps=100,
                link_type="customer",
                status="up",
            )

    return g


def get_nodes_by_type(graph: nx.Graph, node_type: str) -> List[str]:
    """Return all node IDs matching the specified type."""
    return [
        node_id
        for node_id, attrs in graph.nodes(data=True)
        if attrs.get("type") == node_type
    ]


def get_links_by_type(
    graph: nx.Graph, link_type: str
) -> List[Tuple[str, str, Dict[str, Any]]]:
    """Return all edges matching the specified link type with their attributes."""
    return [
        (u, v, attrs)
        for u, v, attrs in graph.edges(data=True)
        if attrs.get("link_type") == link_type
    ]


def get_topology_summary(graph: nx.Graph) -> Dict[str, int]:
    """Return summary counts of nodes and links in the topology."""
    return {
        "core_nodes": len(get_nodes_by_type(graph, "core")),
        "distribution_nodes": len(get_nodes_by_type(graph, "distribution")),
        "access_nodes": len(get_nodes_by_type(graph, "access")),
        "customer_nodes": len(get_nodes_by_type(graph, "customer")),
        "total_nodes": graph.number_of_nodes(),
        "core_links": len(get_links_by_type(graph, "core")),
        "distribution_links": len(get_links_by_type(graph, "distribution")),
        "access_links": len(get_links_by_type(graph, "access")),
        "customer_links": len(get_links_by_type(graph, "customer")),
        "total_links": graph.number_of_edges(),
    }


def print_topology_summary(graph: nx.Graph) -> None:
    """Print human-readable summary of topology node and link counts."""
    summary = get_topology_summary(graph)
    print("=" * 45)
    print("NetPulse AI — Synthetic ISP Network Topology")
    print("=" * 45)
    print(f"Core routers:         {summary['core_nodes']}")
    print(f"Distribution nodes:   {summary['distribution_nodes']}")
    print(f"Access links:         {summary['access_links']}")
    print(f"Access nodes:         {summary['access_nodes']}")
    print(f"Customer endpoints:   {summary['customer_nodes']}")
    print("-" * 45)
    print(f"Total nodes:          {summary['total_nodes']}")
    print(f"Total links:          {summary['total_links']}")
    print("=" * 45)


if __name__ == "__main__":
    topology = build_topology()
    print_topology_summary(topology)
