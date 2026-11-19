# NetPulse AI — Decisions

Decisions are recorded with date, context and status. Reversed decisions stay here with their reversal noted — history is not rewritten.

## 2026-11-18 — Build on simulated infrastructure first

**Decision:** The MVP is built entirely against a network simulator. No real ISP access is required until the MVP works end to end.

**Why:** Safe development, reproducible faults, no dependency on external access.

## 2026-11-18 — Free tiers only

**Decision:** ChatGPT Free, Claude Free and Google Antigravity Individual Free. No purchases, subscriptions, paid APIs or credits.

**Why:** Zero-cost development. Rate limits are accepted as a constraint: when one assistant hits its cap, work moves to another or waits.

## 2026-11-18 — GitHub as the single source of truth

**Decision:** All code, documentation, tasks and history live in GitHub. The three assistants are not directly connected; they share context only through repository files (`docs/PROJECT_CONTEXT.md`, `docs/ARCHITECTURE.md`, `docs/AI_HANDOFF.md`).

**Why:** No integration exists between the three free assistants. Files are the reliable handoff mechanism.

## 2026-11-18 — Public repository, MIT license

**Decision:** The `netpulse-ai` repository is public under the MIT license.

**Why:** Public portfolio project; MIT is the standard permissive default. No secrets are ever committed.

## 2026-11-18 — Stack: Python, Streamlit, Pandas, scikit-learn, NetworkX, SQLite

**Decision:** One language (Python) across simulator, collection, intelligence and dashboard; Streamlit for the UI; SQLite for storage.

**Why:** Fastest path to a working MVP with the team's existing Python experience.

## 2026-11-18 — Feature branches and pull requests, human approval

**Decision:** All work happens on feature branches and merges through pull requests. Nothing merges without the maintainer's approval. Never delete branches, overwrite `main`, or force-push without approval.

## 2026-11-18 — Downstream reachability deferred to diagnosis phase

**Decision:** When a node goes down (`node_down`), attached links report down (status "down", 100% loss, 0.0 latency), but cascading failure propagation to downstream nodes (nodes and links further down the tree behind the failure) is deferred. The simulator reports localized link and node status; full downstream reachability modeling will be decided before the Week 5–6 root-cause diagnosis work.

**Why:** Keeps the Week 1–2 simulator interface clean, fast, and focused on direct fault injection without prematurely coupling simulator logic to path-walking routing logic.

## 2026-11-18 — Telemetry collector owns simulation clock and timestamp semantics

**Decision:** The telemetry collector owns the simulation clock when running against a `Simulator` instance. Stored timestamps represent simulation time. If a source only implements `get_measurements()`, it or the caller must advance time itself. A second consumer must not call `tick()` concurrently as that would double-advance the simulation clock.

**Why:** Keeps time advancement linear and coordinated through the primary ingest pipeline without race conditions or conflicting step increments.

## 2026-11-18 — Telemetry storage limitations and query pagination

**Decision:** Telemetry history is appended into SQLite with no automatic pruning or retention policy for the initial MVP foundation. `query_measurements` supports `order` ("ASC" | "DESC") and `limit` parameters to allow windowed reads for monitoring and dashboard queries. A rolling retention window (e.g. 7-day or 30-day purge) remains deferred.

**Context & Limitations:**
- At default 5-second polling intervals across 59 targets (30 nodes + 29 links), the collector writes ~1,019,520 rows (~189 MB) per day.
- Monitoring and dashboard consumers should use `order="DESC"` and `limit=N` when retrieving recent telemetry rather than scanning full historical tables.

## 2026-11-18 — Tiered threshold rules and rolling trend architecture

**Decision:** Threshold monitoring evaluates telemetry against network tier baselines (`core`, `distribution`, `access`, `customer`, `node`) with two severity tiers (`WARNING` and `CRITICAL`). Directional trends (`rising`, `falling`, `stable`) are calculated using a rolling window of recent measurements per target by comparing the median of the latest k samples (k = max(1, min(3, n // 3))) with the median of the earlier samples, against relative and absolute deltas.

**Why:** Fixed single-value thresholds across all links produce false positives (e.g. 30ms is normal for customer links but critical for core links). Directional trends give operators early warning before hard critical breaches occur and power the Streamlit dashboard without heavy ML dependencies in Week 3.

## 2026-11-18 — Plotly for topology visualisation

**Decision:** Use Plotly Scatter traces for the Streamlit topology graph. Plotly provides interactive pan, hover details, and direct color/width control for the NetworkX node and link model.

**Why:** Plotly integrates cleanly with Streamlit and avoids an additional web rendering dependency such as PyVis.

## 2026-11-18 — Hierarchical deterministic topology layout

**Decision:** Position nodes in deterministic tiers (`core`, `distribution`, `access`, `customer`) and sort numbered names with natural sorting (`cust_2` before `cust_10`). The graph renderer derives all positions locally and does not store layout coordinates in SQLite.

**Why:** A fixed hierarchical layout is reproducible and natural node ordering keeps customer edges aligned without crossing.

## 2026-11-18 — Static topology graph source

**Decision:** The topology graph structure is built by `network/topology.py`; SQLite stores telemetry measurements and monitoring state is populated through `NetworkMonitor.from_db()`.

**Why:** NetworkX topology structure is a configuration/model concern, while SQLite remains the telemetry source. Mixing topology structure into telemetry storage would blur the module boundaries.

## 2026-11-18 — Dashboard remains read-only

**Decision:** The Streamlit dashboard reads SQLite only. It may populate `NetworkMonitor.from_db()` and render topology/monitor status, but it must not import or invoke `Simulator` or `Collector`.

**Why:** Collection belongs to the monitoring pipeline. A read-only dashboard prevents UI actions from advancing simulation state or bypassing the SQLite data flow.

## 2026-11-19 — Empty monitor reports UNKNOWN health

**Decision:** `NetworkMonitor.get_network_status()` now returns `overall_health = "UNKNOWN"` when there are no targets (previously `"HEALTHY"`), which changes the behaviour PR #10 introduced, so later anomaly-detection code must handle `UNKNOWN` rather than treating "not CRITICAL or WARNING" as healthy.

**Why:** An empty database must not display as a healthy network; "no telemetry" is a different state from "telemetry within thresholds".

## 2026-11-19 — Learned anomaly baselines

**Decision:** Anomaly detection learns one robust median/MAD baseline per target from up-status telemetry. It records explicit upper latency/loss bounds with each anomaly and does not call monitoring fixed thresholds.

**Why:** Fixed thresholds describe known health limits, while anomaly detection identifies deviation from the target's own observed normal behavior. MAD bounds reduce sensitivity to isolated outliers and keep node/link baselines independent.

## 2026-11-19 — Anomaly evidence storage

**Decision:** The database layer owns an `anomalies` table and idempotent insert/query helpers. Anomaly rows include the metric, severity, score, JSON evidence, learned baseline values, explicit bounds, and detection method.

**Why:** Intelligence modules must not execute SQL outside the database module, and the evidence must remain available for dashboards and later diagnosis work.
