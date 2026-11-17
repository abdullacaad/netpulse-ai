# Contributing to NetPulse AI

## Workflow

1. ChatGPT prepares a technical task with acceptance criteria.
2. Antigravity implements the task on a feature branch.
3. Antigravity runs the tests.
4. Claude independently reviews the code.
5. ChatGPT checks the implementation against the architecture.
6. The maintainer approves the pull request.
7. Changes merge into `main`.
8. Documentation and the development log are updated.

## Rules

- Work on a feature branch (`feature/<short-name>`). Never commit directly to `main`.
- Never delete branches, overwrite `main`, or force-push without approval.
- Never commit passwords, API keys or other secrets. Use environment variables.
- Every assistant reads `docs/PROJECT_CONTEXT.md` before significant work.
- Record handoffs in `docs/AI_HANDOFF.md` when work moves between assistants.
- Keep the free-tier rule: no paid APIs, subscriptions or credits.
- Simulated infrastructure only until the MVP is working — no real ISP access.

## Pull requests

Use the pull request template. Describe what changed, why, and how it was tested. A pull request merges only after human approval.
