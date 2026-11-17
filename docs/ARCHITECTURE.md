# NetPulse AI — Architecture

## Overview

A modular Python application. Data flows in one direction: the simulator produces a network, the collector measures it, storage keeps the history, the intelligence layer analyses it, and the dashboard presents it.

```text
network/ (simulator)
      |
      v
monitoring/ (telemetry collector) --> database/ (SQLite)
      |                                    |
      v                                    v
intelligence/ (anomaly detection, root-cause diagnosis)
      |
      v
dashboard/ (Streamlit)
```

## Modules

### network/ — simulator and topology

Builds a synthetic ISP network: core routers, distribution nodes, access links and customer endpoints, using NetworkX graphs. Produces realistic latency and packet-loss behaviour, including faults that can be injected (link congestion, node failure, flapping). Nothing here touches a real network.

### monitoring/ — telemetry collector

Polls the simulated network on a schedule and records latency, packet loss and node health per link and node. Applies thresholds and keeps rolling trends. This is the only module that reads live (simulated) state.

### database/ — SQLite storage layer

One SQLite database for all telemetry history: timestamped measurements per node and link, plus detected anomalies and diagnoses. Keeps schema creation and queries in one place so no other module writes SQL directly.

### intelligence/ — anomaly detection and root-cause diagnosis

- **Anomaly detection:** statistical and scikit-learn models over telemetry history flag unusual latency, loss or node behaviour. Baselines are learned from normal simulated traffic; thresholds are explicit and recorded.
- **Root-cause diagnosis:** when an anomaly is flagged, topology-aware correlation walks the graph from affected nodes toward the shared upstream link or node most likely responsible, and reports a ranked list of candidate causes with evidence.

### dashboard/ — Streamlit UI

Reads from the database only. Shows network topology, live latency and loss, active anomalies, diagnoses, and history. No direct access to the simulator or collector.

### src/ — shared code

Configuration, logging and helpers used by more than one module. No business logic lives here.

## Data flow

1. Simulator generates the network and its behaviour.
2. Collector samples measurements and writes them to SQLite.
3. Intelligence reads history from SQLite, flags anomalies, writes diagnoses back.
4. Dashboard reads SQLite and renders the current state.

## Technology choices

- **Python** — the whole stack in one language.
- **Streamlit** — fastest path to a working dashboard.
- **Pandas** — telemetry as time-series tables.
- **scikit-learn** — anomaly detection baselines (isolation forest / statistical models first).
- **NetworkX** — topology as a graph; shortest paths and neighbour lookups for diagnosis.
- **SQLite** — zero-setup storage, enough for MVP telemetry volumes.

## What is not built yet

This document describes the target architecture. At scaffold time (18 Nov 2026) no module is implemented. Implementation order follows `docs/ROADMAP.md`: simulator and collector first, then storage, then intelligence, then the dashboard.
