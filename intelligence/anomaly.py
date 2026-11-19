"""Baseline anomaly detection for NetPulse AI telemetry."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union
import math
import statistics

from database.db import (
    DEFAULT_DB_PATH,
    insert_anomalies,
    list_target_ids,
    query_measurements,
)


@dataclass
class AnomalyBaseline:
    """Robust learned baseline for one target."""

    target_id: str
    target_type: str
    latency_median: Optional[float]
    latency_mad: Optional[float]
    latency_threshold: Optional[float]
    loss_median: Optional[float]
    loss_mad: Optional[float]
    loss_threshold: Optional[float]
    sample_count: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "target_type": self.target_type,
            "baseline_latency_ms": self.latency_median,
            "baseline_loss_pct": self.loss_median,
            "latency_mad_ms": self.latency_mad,
            "loss_mad_pct": self.loss_mad,
            "threshold_latency_ms": self.latency_threshold,
            "threshold_loss_pct": self.loss_threshold,
            "sample_count": self.sample_count,
            "method": "robust-median-mad",
        }


@dataclass
class Anomaly:
    """One detected anomaly with evidence."""

    timestamp: str
    target_type: str
    target_id: str
    anomaly_type: str
    severity: str
    score: float
    evidence: Dict[str, Any]
    baseline_latency_ms: Optional[float]
    baseline_loss_pct: Optional[float]
    threshold_latency_ms: Optional[float]
    threshold_loss_pct: Optional[float]
    method: str = "robust-median-mad"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "anomaly_type": self.anomaly_type,
            "severity": self.severity,
            "score": round(float(self.score), 6),
            "evidence": dict(self.evidence),
            "baseline_latency_ms": self.baseline_latency_ms,
            "baseline_loss_pct": self.baseline_loss_pct,
            "threshold_latency_ms": self.threshold_latency_ms,
            "threshold_loss_pct": self.threshold_loss_pct,
            "method": self.method,
        }


def _median(values: List[float]) -> Optional[float]:
    return round(float(statistics.median(values)), 6) if values else None


def _mad(values: List[float], median_value: Optional[float]) -> Optional[float]:
    if median_value is None or not values:
        return None
    return round(float(statistics.median([abs(value - median_value) for value in values])), 6)


def _upper_bound(median_value: Optional[float], mad_value: Optional[float], metric: str) -> Optional[float]:
    if median_value is None:
        return None
    mad_floor = 3 * 1.4826 * (mad_value or 0.0)
    if metric == "latency":
        relative_floor = abs(median_value) * 0.10
        absolute_floor = 0.5
    else:
        relative_floor = abs(median_value) * 0.20
        absolute_floor = 0.5
    return round(median_value + max(mad_floor, relative_floor, absolute_floor), 6)


class AnomalyDetector:
    """Learns per-target robust baselines and stores flagged anomalies."""

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        minimum_samples: int = 5,
    ) -> None:
        if isinstance(minimum_samples, bool) or not isinstance(minimum_samples, int):
            raise ValueError("minimum_samples must be a positive integer")
        if minimum_samples <= 0:
            raise ValueError("minimum_samples must be a positive integer")
        self.db_path = db_path if db_path is not None else DEFAULT_DB_PATH
        self.minimum_samples = minimum_samples
        self.baselines: Dict[str, AnomalyBaseline] = {}
        self._isolation_forests: Dict[str, Any] = {}

    def fit(self, rows: Iterable[Dict[str, Any]]) -> int:
        """Learn normal baselines by grouping up-status telemetry per target."""
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            status = str(row.get("status", "up")).lower()
            if status != "up":
                continue
            target_id = str(row["target_id"])
            grouped.setdefault(target_id, []).append(dict(row))

        count = 0
        for target_id, normal_rows in grouped.items():
            target_type = str(normal_rows[0].get("target_type", "link"))
            latencies = [
                float(row["latency_ms"])
                for row in normal_rows
                if row.get("latency_ms") is not None
            ]
            losses = [
                float(row["loss_pct"])
                for row in normal_rows
                if row.get("loss_pct") is not None
            ]
            latency_median = _median(latencies)
            loss_median = _median(losses)
            latency_mad = _mad(latencies, latency_median)
            loss_mad = _mad(losses, loss_median)
            baseline = AnomalyBaseline(
                target_id=target_id,
                target_type=target_type,
                latency_median=latency_median,
                latency_mad=latency_mad,
                latency_threshold=_upper_bound(latency_median, latency_mad, "latency"),
                loss_median=loss_median,
                loss_mad=loss_mad,
                loss_threshold=_upper_bound(loss_median, loss_mad, "loss"),
                sample_count=len(normal_rows),
            )
            self.baselines[target_id] = baseline
            count += 1

            if len(normal_rows) >= 8:
                try:
                    import numpy as np
                    from sklearn.ensemble import IsolationForest

                    features = [
                        [float(row["latency_ms"] or 0.0), float(row["loss_pct"] or 0.0)]
                        for row in normal_rows
                        if row.get("latency_ms") is not None or row.get("loss_pct") is not None
                    ]
                    if len(features) >= 8:
                        forest = IsolationForest(
                            n_estimators=100,
                            contamination=0.02,
                            random_state=42,
                        )
                        forest.fit(np.asarray(features, dtype=float))
                        self._isolation_forests[target_id] = forest
                except (ImportError, ValueError):
                    pass
        return count

    def fit_from_db(
        self,
        target_id: Optional[str] = None,
        db_path: Optional[Union[str, Path]] = None,
    ) -> int:
        """Learn baselines from normal telemetry history in SQLite."""
        path = db_path if db_path is not None else self.db_path
        target_ids = [target_id] if target_id is not None else list_target_ids(path)
        normal_rows: List[Dict[str, Any]] = []
        for loaded_target_id in target_ids:
            normal_rows.extend(
                query_measurements(
                    target_id=loaded_target_id,
                    path=path,
                    order="ASC",
                )
            )
        return self.fit(normal_rows)

    def detect(self, measurement: Dict[str, Any]) -> List[Anomaly]:
        """Flag unusual fields in one measurement without fixed monitoring thresholds."""
        target_id = str(measurement["target_id"])
        baseline = self.baselines.get(target_id)
        if baseline is None:
            return []
        if baseline.sample_count < self.minimum_samples:
            return []

        target_type = str(measurement.get("target_type", baseline.target_type))
        timestamp = str(measurement.get("timestamp", ""))
        status = str(measurement.get("status", "up")).lower()
        anomalies: List[Anomaly] = []

        if status == "down":
            anomalies.append(
                Anomaly(
                    timestamp=timestamp,
                    target_type=target_type,
                    target_id=target_id,
                    anomaly_type="node_down" if target_type == "node" else "link_down",
                    severity="CRITICAL",
                    score=1.0,
                    evidence={
                        "observed_status": "down",
                        "baseline_status": "up",
                        "baseline_sample_count": baseline.sample_count,
                    },
                    baseline_latency_ms=baseline.latency_median,
                    baseline_loss_pct=baseline.loss_median,
                    threshold_latency_ms=baseline.latency_threshold,
                    threshold_loss_pct=baseline.loss_threshold,
                )
            )
            return anomalies

        latency = measurement.get("latency_ms")
        if latency is not None and baseline.latency_threshold is not None:
            latency_value = float(latency)
            if latency_value > baseline.latency_threshold:
                baseline_value = baseline.latency_median or 0.0
                relative = (
                    (latency_value - baseline_value) / baseline_value
                    if baseline_value > 0
                    else latency_value
                )
                severity = "CRITICAL" if relative >= 1.0 else "WARNING"
                anomalies.append(
                    Anomaly(
                        timestamp=timestamp,
                        target_type=target_type,
                        target_id=target_id,
                        anomaly_type="latency",
                        severity=severity,
                        score=round(relative, 6),
                        evidence={
                            "observed_latency_ms": latency_value,
                            "baseline_latency_median_ms": baseline.latency_median,
                            "baseline_latency_mad_ms": baseline.latency_mad,
                            "upper_latency_bound_ms": baseline.latency_threshold,
                            "relative_deviation": relative,
                            "baseline_sample_count": baseline.sample_count,
                        },
                        baseline_latency_ms=baseline.latency_median,
                        baseline_loss_pct=baseline.loss_median,
                        threshold_latency_ms=baseline.latency_threshold,
                        threshold_loss_pct=baseline.loss_threshold,
                    )
                )

        loss = measurement.get("loss_pct")
        if loss is not None and baseline.loss_threshold is not None:
            loss_value = float(loss)
            if loss_value > baseline.loss_threshold:
                baseline_value = baseline.loss_median or 0.0
                relative = (
                    (loss_value - baseline_value) / baseline_value
                    if baseline_value > 0
                    else loss_value
                )
                severity = "CRITICAL" if relative >= 2.0 else "WARNING"
                anomalies.append(
                    Anomaly(
                        timestamp=timestamp,
                        target_type=target_type,
                        target_id=target_id,
                        anomaly_type="packet_loss",
                        severity=severity,
                        score=round(relative, 6),
                        evidence={
                            "observed_loss_pct": loss_value,
                            "baseline_loss_median_pct": baseline.loss_median,
                            "baseline_loss_mad_pct": baseline.loss_mad,
                            "upper_loss_bound_pct": baseline.loss_threshold,
                            "relative_deviation": relative,
                            "baseline_sample_count": baseline.sample_count,
                        },
                        baseline_latency_ms=baseline.latency_median,
                        baseline_loss_pct=baseline.loss_median,
                        threshold_latency_ms=baseline.latency_threshold,
                        threshold_loss_pct=baseline.loss_threshold,
                    )
                )

        return anomalies

    def detect_measurements(
        self,
        measurements: Iterable[Dict[str, Any]],
        db_path: Optional[Union[str, Path]] = None,
    ) -> List[Anomaly]:
        """Detect anomalies and persist every result to SQLite."""
        anomalies: List[Anomaly] = []
        for measurement in measurements:
            anomalies.extend(self.detect(measurement))
        if anomalies:
            insert_anomalies(
                [anomaly.to_dict() for anomaly in anomalies],
                db_path if db_path is not None else self.db_path,
            )
        return anomalies

    detect_and_store = detect_measurements


def detect_anomalies(
    normal_history: Iterable[Dict[str, Any]],
    observations: Iterable[Dict[str, Any]],
    db_path: Optional[Union[str, Path]] = None,
    minimum_samples: int = 5,
) -> List[Anomaly]:
    """Convenience function: fit normal history, detect observations, and store anomalies."""
    detector = AnomalyDetector(db_path=db_path, minimum_samples=minimum_samples)
    detector.fit(normal_history)
    return detector.detect_measurements(observations)
