"""Tests for learned-baseline anomaly detection."""

from pathlib import Path

import pytest

from database.db import insert_measurements, query_anomalies
from intelligence.anomaly import AnomalyDetector, detect_anomalies
from network.simulator import Simulator


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    return tmp_path / "anomaly.db"


def test_injected_fault_flags_anomaly_and_persists_evidence(temp_db: Path):
    """Acceptance: congestion produces a baseline anomaly with SQLite evidence."""
    sim = Simulator(seed=42)
    normal = []
    for _ in range(12):
        normal.extend(
            row for row in sim.tick()
            if row["target_id"] == "core_1-dist_1"
        )

    detector = AnomalyDetector(db_path=temp_db)
    detector.fit(normal)
    sim.inject_fault("congestion", ("core_1", "dist_1"), duration=1)
    observation = next(
        row for row in sim.tick()
        if row["target_id"] == "core_1-dist_1"
    )
    anomalies = detector.detect_measurements([observation])

    assert anomalies
    assert any(item.anomaly_type == "latency" for item in anomalies)
    latency_anomaly = next(
        item for item in anomalies if item.anomaly_type == "latency"
    )
    assert latency_anomaly.evidence["observed_latency_ms"] == observation["latency_ms"]
    assert latency_anomaly.evidence["baseline_sample_count"] == 12

    stored = query_anomalies(target_id="core_1-dist_1", path=temp_db)
    assert len(stored) >= 1
    assert stored[0]["evidence"]["observed_latency_ms"] == observation["latency_ms"]


def test_subtle_fault_below_monitoring_warning_is_detected(temp_db: Path):
    """A 20ms distribution latency remains below the 30ms warning threshold but is unusual."""
    normal = [
        {
            "timestamp": f"2026-11-18T12:00:{i:02d}Z",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": 15.0 + (i % 3) * 0.1,
            "loss_pct": 0.05,
            "status": "up",
        }
        for i in range(12)
    ]
    detector = AnomalyDetector(db_path=temp_db)
    detector.fit(normal)
    anomaly = detector.detect(
        {
            "timestamp": "2026-11-18T12:01:00Z",
            "target_type": "link",
            "target_id": "core_1-dist_1",
            "latency_ms": 20.0,
            "loss_pct": 0.05,
            "status": "up",
        }
    )

    assert anomaly
    assert any(item.anomaly_type == "latency" for item in anomaly)
    assert next(item for item in anomaly if item.anomaly_type == "latency").threshold_latency_ms < 30.0


@pytest.mark.parametrize("seed", [42, 43, 44])
def test_no_false_positives_on_healthy_runs_across_seeds(seed: int):
    """Healthy simulator runs must not create baseline anomalies across seeds."""
    sim = Simulator(seed=seed)
    normal = []
    healthy_observations = []
    for tick in range(20):
        rows = sim.tick()
        target_rows = [row for row in rows if row["target_type"] == "link"]
        if tick < 12:
            normal.extend(target_rows)
        else:
            healthy_observations.extend(target_rows)

    detector = AnomalyDetector(db_path=":memory:")
    detector.fit(normal)
    anomalies = []
    for measurement in healthy_observations:
        anomalies.extend(detector.detect(measurement))

    assert anomalies == []


def test_packet_loss_anomaly_has_explicit_evidence(temp_db: Path):
    """Packet-loss deviations are learned independently and persist evidence."""
    normal = [
        {
            "timestamp": f"2026-11-18T12:00:{i:02d}Z",
            "target_type": "link",
            "target_id": "dist_1-access_1",
            "latency_ms": 30.0,
            "loss_pct": 0.05 + (i % 2) * 0.01,
            "status": "up",
        }
        for i in range(12)
    ]
    observation = {
        "timestamp": "2026-11-18T12:01:00Z",
        "target_type": "link",
        "target_id": "dist_1-access_1",
        "latency_ms": 30.0,
        "loss_pct": 1.0,
        "status": "up",
    }
    anomalies = detect_anomalies(normal, [observation], db_path=temp_db)

    assert any(item.anomaly_type == "packet_loss" for item in anomalies)
    packet = next(item for item in anomalies if item.anomaly_type == "packet_loss")
    assert packet.evidence["observed_loss_pct"] == 1.0
    assert packet.threshold_loss_pct is not None
    assert packet.method == "robust-median-mad"


def test_node_down_is_anomaly_even_when_monitor_health_is_unknown():
    """Down node behavior is detected without assuming HEALTHY/WARNING/CRITICAL status."""
    normal = [
        {
            "timestamp": f"2026-11-18T12:00:{i:02d}Z",
            "target_type": "node",
            "target_id": "dist_1",
            "latency_ms": 1.0,
            "loss_pct": 0.0,
            "status": "up",
        }
        for i in range(10)
    ]
    detector = AnomalyDetector(db_path=":memory:")
    detector.fit(normal)
    anomalies = detector.detect(
        {
            "timestamp": "2026-11-18T12:01:00Z",
            "target_type": "node",
            "target_id": "dist_1",
            "latency_ms": 0.0,
            "loss_pct": 100.0,
            "status": "down",
        }
    )

    assert len(anomalies) == 1
    assert anomalies[0].anomaly_type == "node_down"
    assert anomalies[0].evidence["baseline_status"] == "up"


def test_fit_from_db_learns_per_target_without_measurement_threshold_rules(temp_db: Path):
    """Detector loads normal SQLite history and learns its own target baselines."""
    rows = []
    for i in range(10):
        rows.append(
            {
                "timestamp": f"2026-11-18T12:00:{i:02d}Z",
                "target_type": "link",
                "target_id": "core_1-dist_1",
                "latency_ms": 15.0,
                "loss_pct": 0.1,
                "status": "up",
            }
        )
    insert_measurements(rows, temp_db)
    detector = AnomalyDetector(db_path=temp_db)

    assert detector.fit_from_db(db_path=temp_db) == 1
    assert detector.baselines["core_1-dist_1"].latency_threshold == pytest.approx(16.5)
