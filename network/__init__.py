"""NetPulse AI network module: synthetic ISP topology generation and simulation."""

from .topology import (
    build_topology,
    get_links_by_type,
    get_nodes_by_type,
    get_topology_summary,
)
from .simulator import Simulator

__all__ = [
    "build_topology",
    "get_nodes_by_type",
    "get_links_by_type",
    "get_topology_summary",
    "Simulator",
]

