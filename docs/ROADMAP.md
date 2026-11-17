# NetPulse AI — Roadmap (6-week MVP)

## Week 1–2 — Foundation and simulator

- Project setup, repository, environment (done 18 Nov 2026)
- Network simulator: synthetic ISP topology (core, distribution, access, customers) with NetworkX
- Telemetry collector: scheduled sampling of latency, packet loss and node health
- SQLite storage layer: schema and write/read helpers
- First end-to-end check: simulate → collect → store → read back

## Week 3–4 — Monitoring and topology

- Latency and packet-loss monitoring: thresholds, rolling trends, per-link and per-node views
- Topology visualisation: interactive NetworkX graph in the dashboard
- Basic Streamlit dashboard skeleton over the stored telemetry

## Week 5–6 — Intelligence and MVP polish

- Anomaly detection: baselines from normal simulated traffic, flagged anomalies with evidence
- Root-cause diagnosis: topology-aware correlation, ranked candidate causes
- Dashboard completion: anomalies, diagnoses, history
- Tests across modules, documentation pass, MVP demo and release notes

## Feature checklist

- [ ] Network simulator
- [ ] Telemetry collector
- [ ] Latency and packet-loss monitoring
- [ ] Network topology visualisation
- [ ] Anomaly detection
- [ ] Root-cause diagnosis
- [ ] Monitoring dashboard

## After the MVP

Real ISP data source (only after the simulated MVP works), alerting, multi-user access, and deployment — all out of scope for the six weeks.
