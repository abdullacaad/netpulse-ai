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

## 2026-11-18 — Telemetry storage limitations and retention deferral

**Decision:** Telemetry history is appended into SQLite with no automatic pruning or retention policy for the initial MVP foundation. `query_measurements` currently operates without a `LIMIT` clause.

**Context & Limitations:**
- At default 5-second polling intervals across 59 targets (30 nodes + 29 links), the collector writes ~1,019,520 rows (~189 MB) per day.
- A rolling retention window (e.g. 7-day or 30-day purge) and query pagination/limits will be introduced in Week 3–4 when monitoring thresholds and dashboard queries are integrated.
