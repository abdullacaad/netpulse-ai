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
