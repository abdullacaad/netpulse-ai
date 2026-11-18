"""Monitoring threshold rules and breach detection for NetPulse AI.

Defines configurable metric thresholds per tier and evaluates
telemetry measurements for latency, packet-loss, and status breaches.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def get_target_tier(target_id: str, target_type: str = "link") -> str:
    """Infer the network tier ('core', 'distribution', 'access', 'customer') for a target ID."""
    target_id_lower = target_id.lower()

    # Core
    if target_id_lower.startswith("core_") and "-" not in target_id_lower:
        return "core"
    if "core_" in target_id_lower and "dist_" not in target_id_lower:
        return "core"

    # Distribution
    if target_id_lower.startswith("dist_") and "-" not in target_id_lower:
        return "distribution"
    if "core_" in target_id_lower and "dist_" in target_id_lower:
        return "distribution"
    if target_id_lower.startswith("dist_") and "access_" not in target_id_lower:
        return "distribution"

    # Access
    if target_id_lower.startswith("access_") and "-" not in target_id_lower:
        return "access"
    if "dist_" in target_id_lower and "access_" in target_id_lower:
        return "access"

    # Customer
    if target_id_lower.startswith("cust_") and "-" not in target_id_lower:
        return "customer"
    if "access_" in target_id_lower and "cust_" in target_id_lower:
        return "customer"

    return "access" if target_type == "link" else "node"


@dataclass
class ThresholdConfig:
    """Configurable threshold rules for network metrics across tiers.

    Attributes:
        core_latency_warn_ms: Warning threshold for core links (~5ms baseline).
        core_latency_crit_ms: Critical threshold for core links.
        distribution_latency_warn_ms: Warning threshold for distribution links (~15ms baseline).
        distribution_latency_crit_ms: Critical threshold for distribution links.
        access_latency_warn_ms: Warning threshold for access links (~30ms baseline).
        access_latency_crit_ms: Critical threshold for access links.
        customer_latency_warn_ms: Warning threshold for customer links (~30ms baseline).
        customer_latency_crit_ms: Critical threshold for customer links.
        node_latency_warn_ms: Warning threshold for node processing latency (~1ms baseline).
        node_latency_crit_ms: Critical threshold for node processing latency.
        default_latency_warn_ms: Fallback warning threshold for unknown tiers.
        default_latency_crit_ms: Fallback critical threshold for unknown tiers.
        loss_warn_pct: Warning threshold for packet loss percentage.
        loss_crit_pct: Critical threshold for packet loss percentage.
        custom_thresholds: Per-target overrides: {target_id: {'latency_warn_ms': ..., ...}}.
    """

    core_latency_warn_ms: float = 10.0
    core_latency_crit_ms: float = 20.0

    distribution_latency_warn_ms: float = 30.0
    distribution_latency_crit_ms: float = 60.0

    access_latency_warn_ms: float = 50.0
    access_latency_crit_ms: float = 100.0

    customer_latency_warn_ms: float = 50.0
    customer_latency_crit_ms: float = 100.0

    node_latency_warn_ms: float = 5.0
    node_latency_crit_ms: float = 10.0

    default_latency_warn_ms: float = 50.0
    default_latency_crit_ms: float = 100.0

    loss_warn_pct: float = 2.0
    loss_crit_pct: float = 5.0

    custom_thresholds: Dict[str, Dict[str, float]] = field(default_factory=dict)

    def get_thresholds_for_target(
        self, target_id: str, target_type: str = "link", tier: Optional[str] = None
    ) -> Dict[str, float]:
        """Return warning and critical thresholds for a specific target."""
        if tier is None:
            tier = get_target_tier(target_id, target_type)

        if target_type == "node":
            warn_lat = self.node_latency_warn_ms
            crit_lat = self.node_latency_crit_ms
        elif tier == "core":
            warn_lat = self.core_latency_warn_ms
            crit_lat = self.core_latency_crit_ms
        elif tier == "distribution":
            warn_lat = self.distribution_latency_warn_ms
            crit_lat = self.distribution_latency_crit_ms
        elif tier == "access":
            warn_lat = self.access_latency_warn_ms
            crit_lat = self.access_latency_crit_ms
        elif tier == "customer":
            warn_lat = self.customer_latency_warn_ms
            crit_lat = self.customer_latency_crit_ms
        else:
            warn_lat = self.default_latency_warn_ms
            crit_lat = self.default_latency_crit_ms

        warn_loss = self.loss_warn_pct
        crit_loss = self.loss_crit_pct

        # Apply target-specific overrides if present
        if target_id in self.custom_thresholds:
            overrides = self.custom_thresholds[target_id]
            warn_lat = overrides.get("latency_warn_ms", warn_lat)
            crit_lat = overrides.get("latency_crit_ms", crit_lat)
            warn_loss = overrides.get("loss_warn_pct", warn_loss)
            crit_loss = overrides.get("loss_crit_pct", crit_loss)

        return {
            "latency_warn_ms": warn_lat,
            "latency_crit_ms": crit_lat,
            "loss_warn_pct": warn_loss,
            "loss_crit_pct": crit_loss,
        }


@dataclass
class Breach:
    """Represents an active threshold or status breach."""

    target_id: str
    target_type: str
    tier: str
    metric: str  # "latency" | "packet_loss" | "status"
    severity: str  # "WARNING" | "CRITICAL"
    current_value: Any
    threshold_value: Any
    timestamp: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert breach instance to dict."""
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "tier": self.tier,
            "metric": self.metric,
            "severity": self.severity,
            "current_value": self.current_value,
            "threshold_value": self.threshold_value,
            "timestamp": self.timestamp,
            "message": self.message,
        }


def evaluate_measurement(
    measurement: Dict[str, Any],
    thresholds: Optional[ThresholdConfig] = None,
    tier: Optional[str] = None,
) -> List[Breach]:
    """Evaluate a single measurement dict against threshold rules.

    Args:
        measurement: Dict with keys: timestamp, target_type, target_id, latency_ms, loss_pct, status.
        thresholds: Optional ThresholdConfig instance (defaults to ThresholdConfig()).
        tier: Optional tier string. If None, inferred from target_id.

    Returns:
        List of Breach objects representing any triggered breaches.
    """
    if thresholds is None:
        thresholds = ThresholdConfig()

    target_id = str(measurement["target_id"])
    target_type = str(measurement.get("target_type", "link"))
    timestamp = str(measurement.get("timestamp", ""))
    status = str(measurement.get("status", "up")).lower()
    latency_ms = measurement.get("latency_ms")
    loss_pct = measurement.get("loss_pct")

    if tier is None:
        tier = get_target_tier(target_id, target_type)

    rules = thresholds.get_thresholds_for_target(target_id, target_type, tier)
    breaches: List[Breach] = []

    # 1. Status breach (target is down)
    if status == "down":
        breaches.append(
            Breach(
                target_id=target_id,
                target_type=target_type,
                tier=tier,
                metric="status",
                severity="CRITICAL",
                current_value="down",
                threshold_value="up",
                timestamp=timestamp,
                message=f"{target_type.capitalize()} '{target_id}' is down.",
            )
        )

    # 2. Packet loss breaches
    if loss_pct is not None:
        loss_val = float(loss_pct)
        if loss_val >= rules["loss_crit_pct"]:
            breaches.append(
                Breach(
                    target_id=target_id,
                    target_type=target_type,
                    tier=tier,
                    metric="packet_loss",
                    severity="CRITICAL",
                    current_value=round(loss_val, 3),
                    threshold_value=rules["loss_crit_pct"],
                    timestamp=timestamp,
                    message=(
                        f"Packet loss {loss_val:.2f}% exceeds critical threshold "
                        f"of {rules['loss_crit_pct']}%."
                    ),
                )
            )
        elif loss_val >= rules["loss_warn_pct"]:
            breaches.append(
                Breach(
                    target_id=target_id,
                    target_type=target_type,
                    tier=tier,
                    metric="packet_loss",
                    severity="WARNING",
                    current_value=round(loss_val, 3),
                    threshold_value=rules["loss_warn_pct"],
                    timestamp=timestamp,
                    message=(
                        f"Packet loss {loss_val:.2f}% exceeds warning threshold "
                        f"of {rules['loss_warn_pct']}%."
                    ),
                )
            )

    # 3. Latency breaches (only evaluated when link is up or loss < 100%)
    if latency_ms is not None and status != "down" and (loss_pct is None or float(loss_pct) < 100.0):
        lat_val = float(latency_ms)
        if lat_val >= rules["latency_crit_ms"]:
            breaches.append(
                Breach(
                    target_id=target_id,
                    target_type=target_type,
                    tier=tier,
                    metric="latency",
                    severity="CRITICAL",
                    current_value=round(lat_val, 2),
                    threshold_value=rules["latency_crit_ms"],
                    timestamp=timestamp,
                    message=(
                        f"Latency {lat_val:.2f}ms exceeds critical threshold "
                        f"of {rules['latency_crit_ms']:.2f}ms."
                    ),
                )
            )
        elif lat_val >= rules["latency_warn_ms"]:
            breaches.append(
                Breach(
                    target_id=target_id,
                    target_type=target_type,
                    tier=tier,
                    metric="latency",
                    severity="WARNING",
                    current_value=round(lat_val, 2),
                    threshold_value=rules["latency_warn_ms"],
                    timestamp=timestamp,
                    message=(
                        f"Latency {lat_val:.2f}ms exceeds warning threshold "
                        f"of {rules['latency_warn_ms']:.2f}ms."
                    ),
                )
            )

    return breaches
