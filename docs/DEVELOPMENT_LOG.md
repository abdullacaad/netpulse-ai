# NetPulse AI — Development Log

Record of what was done, when, and by whom. Newest entries at the top.

## 2026-11-18 — Network simulator implementation (Issue #7)

- Branch: `feature/simulator` created from `main`.
- Implemented `network/topology.py`: synthetic ISP network as a NetworkX graph with 2 core routers, 4 distribution nodes, 8 access nodes/links, and 16 customer endpoints (30 nodes, 29 links).
- Configured baseline latency and attributes: core links ~5ms, distribution links ~15ms, access/customer links ~30ms, healthy loss < 0.5%.
- Implemented `network/simulator.py`: `Simulator` class with reproducible fixed random seed, tick step advancement, telemetry measurement generation (`{timestamp, target_type, target_id, latency_ms, loss_pct, status}`), and fault injection (`congestion`, `node_down`, `flapping`) with duration tracking and manual/auto clearing.
- Created `network/__init__.py` exporting public classes and helpers.
- Added `pytest.ini` and created comprehensive test suite `tests/test_simulator.py` (19 tests covering topology node/link counts, attributes, connectivity, simulator schema, seed reproducibility, fault injection and restoration).
- All 19 tests passing.
- Changes kept locally on `feature/simulator` without pushing, ready for review.

## 2026-11-18 — Project setup and repository scaffold

- Project started: NetPulse AI, intelligent ISP network monitoring, anomaly detection and root-cause diagnosis.
- Free multi-AI workflow agreed: ChatGPT Free (planning/architecture/review), Claude Free (independent review), Google Antigravity Individual Free (primary coding), GitHub as source of truth.
- Environment verified on the maintainer's Windows machine: Git 2.56.0, Python 3.14.5, VS Code 1.144.0. Antigravity already installed. ChatGPT Free and Claude Free signed in.
- GitHub connected to Muse (account abdullacaad). Direct repository creation through the GitHub App failed (403 — the App cannot create user repositories), so the repository was created through the browser instead.
- Public repository created: https://github.com/abdullacaad/netpulse-ai (empty, no README, no license at creation).
- Initial scaffold pushed to `main`: README, requirements.txt (streamlit, pandas, scikit-learn, networkx, pytest), MIT LICENSE, CONTRIBUTING.md, .gitignore, docs (PROJECT_CONTEXT, ARCHITECTURE, DEVELOPMENT_LOG, DECISIONS, AI_HANDOFF, ROADMAP), .github pull request template, and module directories.
- Local project directory: `E:\netpulse-ai` (maintainer's machine).
