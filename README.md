# NetPulse AI

Intelligent ISP network monitoring, anomaly detection and root-cause diagnosis platform.

Small ISPs and network teams spot outages from customer complaints — after the damage is done. NetPulse AI watches the network itself: it simulates and collects telemetry, monitors latency and packet loss, visualises topology, detects anomalies and traces them to a likely root cause, all on one dashboard.

## MVP features (6 weeks)

1. Network simulator — synthetic ISP infrastructure for safe development
2. Telemetry collector — gathers latency, packet loss and node health
3. Latency and packet-loss monitoring
4. Network topology visualisation
5. Anomaly detection
6. Root-cause diagnosis
7. Monitoring dashboard

## Stack

Python, Streamlit, Pandas, scikit-learn, NetworkX, SQLite. Simulated infrastructure first — no real ISP access is needed to build the MVP.

## Repository structure

```text
src/           shared application code
monitoring/    telemetry collection, latency and packet-loss monitoring
intelligence/  anomaly detection and root-cause diagnosis
network/       network simulator and topology
database/      SQLite storage layer
dashboard/     Streamlit dashboard
tests/         automated tests
docs/          project context, architecture, decisions, roadmap, handoffs
data/          sample and simulated data
.github/       pull request template
```

## Quickstart

```bash
git clone https://github.com/abdullacaad/netpulse-ai.git
cd netpulse-ai
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## How this project is built

Three AI assistants work on NetPulse AI using only free tiers, with GitHub as the single source of truth:

- **ChatGPT Free** — project planning, system architecture, research, technical review
- **Claude Free** — independent code review, debugging, documentation review
- **Google Antigravity (Individual, free)** — primary coding agent

They are not directly connected to each other. Context is shared through this repository: every assistant reads `docs/PROJECT_CONTEXT.md` before significant work, and work passed between assistants is recorded in `docs/AI_HANDOFF.md`. Changes go through feature branches and pull requests, merged only after human approval.

## Status

MVP in progress. See `docs/ROADMAP.md` for the six-week plan and `docs/DEVELOPMENT_LOG.md` for what has been done so far.

## License

MIT — see `LICENSE`.
