# NetPulse AI — Project Context

**Every AI assistant must read this file before performing significant work.**

## What NetPulse AI is

An intelligent ISP network monitoring, anomaly detection and root-cause diagnosis platform. It watches a network, spots abnormal behaviour, traces it to a likely cause, and shows everything on a dashboard — so problems are found by the system, not by angry customers.

## The problem

Small ISPs and network teams usually learn about outages from customer complaints. By then users are already affected, and engineers start fault-finding with no clear picture of where the problem is.

## What the MVP does

1. Network simulator — synthetic ISP infrastructure (routers, links, customers) for safe development
2. Telemetry collector — gathers latency, packet loss and node health over time
3. Latency and packet-loss monitoring — thresholds and trends per link and node
4. Network topology visualisation — the network as a graph (NetworkX)
5. Anomaly detection — flags unusual latency, loss or node behaviour (scikit-learn)
6. Root-cause diagnosis — traces an anomaly to the most likely faulty node or link
7. Monitoring dashboard — Streamlit UI over all of the above

## Who it is for

Small ISPs and network operations teams that cannot afford enterprise network monitoring suites.

## Stack

Python, Streamlit, Pandas, scikit-learn, NetworkX, SQLite. Simulated infrastructure first — the MVP must work end to end on simulated data before any real ISP access is considered.

## Repository layout

- `src/` — shared application code
- `monitoring/` — telemetry collection, latency and packet-loss monitoring
- `intelligence/` — anomaly detection and root-cause diagnosis
- `network/` — network simulator and topology
- `database/` — SQLite storage layer
- `dashboard/` — Streamlit dashboard
- `tests/` — automated tests
- `docs/` — this file, architecture, decisions, roadmap, handoffs, development log
- `data/` — sample and simulated data

## How the AI team works

Three AI assistants, all on free tiers, coordinated through GitHub:

| Assistant | Role |
|---|---|
| ChatGPT Free | Project manager, system architect, research analyst, technical decision-maker, code review and QA |
| Claude Free | Independent code reviewer — bugs, security problems, challenging architectural decisions, optimisations, documentation review |
| Google Antigravity (Individual, free) | Primary developer — writes Python code, creates modules, implements features, runs tests, debugs, refactors, maintains documentation |
| GitHub | Shared source of truth — code, docs, tasks, version history, review and merge |

The three assistants are **not** directly connected or synchronised. They share context only through this repository: this file, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md` and `docs/AI_HANDOFF.md`.

## Development workflow

1. ChatGPT prepares a technical task and acceptance criteria.
2. Antigravity implements the task.
3. Antigravity runs tests.
4. Changes are committed to a feature branch.
5. Claude independently reviews the code.
6. ChatGPT evaluates the implementation against the architecture.
7. The maintainer approves the pull request.
8. Changes merge into `main`.
9. Documentation and the development log are updated.

## Rules

- Everything uses free tiers. No purchases, subscriptions or paid APIs.
- Free-tier rate limits apply — expect message and usage caps, and switch tools when one is exhausted.
- Never commit passwords, API keys or other secrets.
- Never delete branches, overwrite `main`, or force-push without approval.
- Never claim a feature is complete until it is implemented, tested and merged.
- Never publish anything or message anyone without the maintainer's approval.
- Simulated infrastructure only until the MVP works.
