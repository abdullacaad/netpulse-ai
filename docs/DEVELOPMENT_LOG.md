# NetPulse AI — Development Log

Record of what was done, when, and by whom. Newest entries at the top.

## 2026-11-18 — Network topology visualisation (Issue #4)

- Branch: `feature/topology` created from `main`.
- Implemented `dashboard/topology.py`:
  - Deterministic hierarchical positions for core, distribution, access, and customer tiers.
  - Interactive Plotly rendering of all 30 nodes and 29 NetworkX links.
  - Node colors reflect `NetworkMonitor` health (`HEALTHY`, `WARNING`, `CRITICAL`, `UNKNOWN`).
  - Link colors reflect current monitoring status and latency/packet-loss health; line width includes packet-loss severity.
  - Node and link hover details expose status, health, latency, and packet loss.
- Implemented `dashboard/app.py`:
  - Streamlit dashboard entry point.
  - Loads `NetworkMonitor` from SQLite with `from_db()`.
  - Reads SQLite only via `NetworkMonitor.from_db()`; sidebar slider sets the rolling window.
- Updated `requirements.txt` with `plotly`.
- Added `tests/test_dashboard.py` covering full topology counts, deterministic layout, monitor-driven node/link colors, down targets, and SQLite read-model loading.
- Full test suite passing (88/88 tests across simulator, database, collector, monitoring, and dashboard).

## 2026-11-18 — Latency and packet-loss monitoring (thresholds and trends) (Issue #3)

- Branch: `feature/monitoring` created from `main`.
- Implemented `monitoring/rules.py`:
  - `get_target_tier(target_id, target_type)`: infers network tier (`core`, `distribution`, `access`, `customer`, `node`).
  - `ThresholdConfig`: configurable warning and critical thresholds per tier (Core: 10/20ms; Distribution: 30/60ms; Access/Customer: 50/100ms; Node: 5/10ms; Loss: 2%/5%) plus per-target overrides.
  - `Breach` dataclass: encapsulates target, metric (`latency`, `packet_loss`, `status`), severity (`WARNING`, `CRITICAL`), current value, threshold, timestamp, and message.
  - `evaluate_measurement()`: validates telemetry measurements against thresholds and status down conditions.
- Implemented `monitoring/trends.py`:
  - `RollingTrendTracker`: rolling window (default 20 samples) of telemetry measurements per target.
  - Computes count, current, rolling average, min, max for latency and loss.
  - Computes directional trends (`rising`, `falling`, `stable`) by comparing the median of the latest k samples (k = max(1, min(3, n // 3))) with the median of earlier samples.
- Implemented `monitoring/monitor.py`:
  - `NetworkMonitor`: orchestrates rules evaluation and rolling trend tracking.
  - Exposes dashboard-ready methods: `get_target_status(target_id)`, `get_network_status()`, `get_breaching_targets()`, `get_all_breaches()`.
  - Integrates with SQLite via `load_from_db()` and `NetworkMonitor.from_db(db_path)`.
  - Included interactive demo runnable via `python -m monitoring.monitor`.
- Updated `database/db.py`:
  - Extended `query_measurements()` with optional `order: str = "ASC"` and `limit: Optional[int] = None` parameters.
- Updated `monitoring/__init__.py`:
  - Exported `Collector`, `NetworkMonitor`, `ThresholdConfig`, `Breach`, `RollingTrendTracker`, `evaluate_measurement`, and `get_target_tier` using PEP 562 lazy attribute loading to avoid circular imports.
- Created test suites and verification:
  - `tests/test_monitoring.py` (17 tests covering tier inference, threshold configuration, healthy/warning/critical evaluations, packet loss breaches, node down breaches, rolling window statistics, directional trend calculation, acceptance test with injected congestion and rising trend, network health aggregation, fault recovery, bounded database loading, immutable status getters, and database round-trip).
  - `tests/test_db.py` (added `test_query_order_and_limit`, bringing total to 13 tests).
  - Full test suite passing (77/77 tests across simulator, database, collector, and monitoring).


## 2026-11-18 — Telemetry collector and SQLite storage layer (Issue #5)

- Branch: `feature/collector` created from `main`.
- Implemented `database/db.py`: SQLite storage layer with `measurements` table (id, timestamp, target_type, target_id, latency_ms, loss_pct, status) and indexes on `(target_id, timestamp, target_type)` (unique constraint for idempotency) and `(timestamp)`. Provides `init_db(path)`, `insert_measurements(rows, path)`, `query_measurements(target_id, start, end, path)`, and `get_connection(path)`.
- Applied PR #9 review fixes: single connection per operation with `_open()` in WAL mode; UTC timestamp normalisation (`_to_utc_iso`); idempotent inserts (`INSERT OR IGNORE`) returning rows actually inserted; rejection of `:memory:` paths with ValueError; strict validation of `poll_interval` (> 0 and finite); prompt loop termination using `threading.Event`; documented polling contract; step_interval_seconds=1 in demo; updated `.gitignore` with WAL/SHM/journal patterns.
- Implemented `monitoring/collector.py`: `Collector` class taking a simulator instance, poll interval (default 5s), and database path. Implements `collect_once()` with error-logging resilience, and `run(duration_seconds)` with prompt interruption via `stop()`.
- Created package exports in `database/__init__.py` and `monitoring/__init__.py`.
- Created automated test suites:
  - `tests/test_db.py` (12 tests covering table creation, WAL mode, unique index, idempotent duplicate batch insertion, UTC timestamp normalisation, target_id and timestamp filtering, ordering, directory creation, `:memory:` rejection).
  - `tests/test_collector.py` (11 tests covering round-trip storage, history accumulation, fault recording in SQLite, error logging on simulator failure, get-only simulator idempotency, invalid poll interval rejection, prompt sleep interruption via threading.Event, and intermittent failure resilience).
- All 49 tests passing (`pytest`). Pushed to `feature/collector`.

## 2026-11-18 — Network simulator implementation (Issue #7)

- Branch: `feature/simulator` created from `main`.
- Implemented `network/topology.py`: synthetic ISP network as a NetworkX graph with 2 core routers, 4 distribution nodes, 8 access nodes/links, and 16 customer endpoints (30 nodes, 29 links).
- Configured baseline latency and attributes: core links ~5ms, distribution links ~15ms, access/customer links ~30ms, healthy loss < 0.5%.
- Implemented `network/simulator.py`: `Simulator` class with reproducible fixed random seed, tick step advancement, telemetry measurement generation (`{timestamp, target_type, target_id, latency_ms, loss_pct, status}`), and fault injection (`congestion`, `node_down`, `flapping`) with duration tracking and manual/auto clearing.
- Created `network/__init__.py` exporting public classes and helpers.
- Added `pytest.ini` and created comprehensive test suite `tests/test_simulator.py` (26 tests covering topology node/link counts, attributes, connectivity, simulator schema, seed reproducibility, fault injection and restoration).
- Applied PR #8 review fixes: attached links go down on `node_down` (status "down", 100% loss); `get_measurements()` returns copies and documents staleness; default `base_time` set to `datetime.now(timezone.utc)`; RNG jitter drawn unconditionally to keep targets independent; duration strictly validated (rejects bool, NaN, float); `clear_fault` safely handles unhashable targets.
- All 26 tests passing.

## 2026-11-18 — Project setup and repository scaffold

- Project started: NetPulse AI, intelligent ISP network monitoring, anomaly detection and root-cause diagnosis.
- Free multi-AI workflow agreed: ChatGPT Free (planning/architecture/review), Claude Free (independent review), Google Antigravity Individual Free (primary coding), GitHub as source of truth.
- Environment verified on the maintainer's Windows machine: Git 2.56.0, Python 3.14.5, VS Code 1.144.0. Antigravity already installed. ChatGPT Free and Claude Free signed in.
- GitHub connected to Muse (account abdullacaad). Direct repository creation through the GitHub App failed (403 — the App cannot create user repositories), so the repository was created through the browser instead.
- Public repository created: https://github.com/abdullacaad/netpulse-ai (empty, no README, no license at creation).
- Initial scaffold pushed to `main`: README, requirements.txt (streamlit, pandas, scikit-learn, networkx, pytest), MIT LICENSE, CONTRIBUTING.md, .gitignore, docs (PROJECT_CONTEXT, ARCHITECTURE, DEVELOPMENT_LOG, DECISIONS, AI_HANDOFF, ROADMAP), .github pull request template, and module directories.
- Local project directory: `E:\netpulse-ai` (maintainer's machine).
