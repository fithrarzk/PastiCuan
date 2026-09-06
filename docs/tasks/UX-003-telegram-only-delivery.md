# UX-003: Telegram-only delivery

- Status: review
- Priority: P1
- Owner/model: root orchestrator (GPT-5) with independent Standards and Spec review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/agents/delivery-lanes.md`, `docs/architecture/system-map.md`, `docs/specs/ci-cd-contract.md`, `DEPLOY_FREE.md`, and exact owned files; target 30k tokens, High-risk-lane maximum 60k
- Retry ceiling: three bounded red-green correction cycles
- Escalation condition: any required change to Telegram webhook/runtime behavior, a production workflow, evidence/research semantics, migration/schema/grants, credentials, or publication gates
- Parallelism: one root writer; two fresh read-only reviewers after implementation
- Base SHA: `1f5651d33bc2d41ffe99b1c8aad0515e7b3360b5`
- Branch: `refactor/UX-003-telegram-only`
- Worktree: `../PastiCuan-wt/ux-003-telegram-only`
- Depends on: none
- File ownership: `.dockerignore`, `.env.example`, `.github/workflows/{ci,validate-branch}.yml`, `.gitignore`, `.streamlit/config.toml`, `AGENTS.md`, `DEPLOY_FREE.md`, `README.md`, `app.py`, `analysis/{contracts,engine,presentation,scanner}.py`, `requirements.txt`, `scripts/ci/check_dependencies.sh`, `tests/test_ci_gates.py`, `tests/test_reliability.py`, `tests/test_yfinance_compat.py`, `ui/**`, `docs/architecture/system-map.md`, `docs/tasks/ROADMAP.md`, `docs/tasks/CLAIMS.md`, and this card
- Merge policy: autonomous

## Outcome

Remove the standalone Streamlit application and its install/deployment surface so the repository has one user-facing product: the Telegram chatbot.

## Non-goals

Do not remove or change `bot.py`, `bot_webhook.py`, FastAPI, Docker, Railway, Render, or the `/` and `/ready` endpoints because they deliver and monitor Telegram webhook traffic. Do not change analysis, evidence, source, freshness, point-in-time, publication, migration, schema, credential, or production data behavior.

## Current evidence

`origin/main` exposes two presentation surfaces: the Streamlit entry point in `app.py` with `ui/**`, `.streamlit/config.toml`, and `requirements.txt`; and the Telegram bot delivered by polling or the FastAPI webhook. CI separately audits the Streamlit dependency profile even though production Railway uses only `requirements-bot.txt`.

## Invariants

- Telegram polling and webhook entry points, health checks, container build, and runtime dependencies remain intact.
- Research commands continue to consume the same signed published snapshots and fail closed under the same gates.
- CI continues auditing every retained runtime/job/CI dependency profile.
- Historical task records remain historical; active architecture, deployment, and roadmap documentation describe Telegram-only delivery.

## Implementation contract

1. Add a repository-surface test proving the standalone web entry point, UI package, Streamlit configuration, and Streamlit dependency profile are absent while Telegram delivery remains.
2. Delete `app.py`, `ui/**`, `.streamlit/config.toml`, and `requirements.txt`.
3. Remove the retired dependency profile from the audit wrapper and update affected compatibility tests without weakening bot dependency coverage.
4. Remove active Streamlit instructions and replace the future cross-surface roadmap item with Telegram-only consistency work.
5. Preserve Telegram hosting and verify focused tests before filing the PR.
6. Configure pip caching against explicit retained dependency profiles so deleting the conventional root `requirements.txt` cannot disable required checks.

## Acceptance tests

- The repository-surface test fails before removal and passes afterward.
- `requirements-bot.txt`, `requirements-jobs.txt`, and `requirements-ci.txt` remain strictly audited.
- Telegram modules compile and existing Telegram/reliability tests pass.
- `rg` finds no active Streamlit runtime/deployment references outside historical task records.
- Required CI is green on the current PR head.
- Both ordinary and exact-head validation workflows use explicit existing files for every enabled pip cache.

## Rollout and rollback

The merge removes only the unneeded Streamlit deployment surface. Railway may rebuild the unchanged Telegram container from `main`; research workflows should not run for presentation/docs-only paths under current workflow policy. Roll back with a normal revert if the deleted standalone interface is required again.

## Handoff

Implementation from base `1f5651d` deletes the Streamlit entry point,
package, configuration, and dependency profile while retaining Telegram polling,
webhook, container, and provider compatibility. The red delivery-surface test
failed on `app.py`; after removal, 22 focused tests passed. A clean Python 3.12
environment passed compilation, all 160 tests, research-release integrity,
strict audits of all three retained dependency profiles, Ruff, shell syntax,
and `git diff --check`. The initial local full-suite failure was diagnosed as
the pre-existing developer environment having yfinance 1.2.0 instead of the
retained 1.5.2 pin; the clean pinned environment passed. No production action,
formula/release change, migration, or credential use occurred. PR, required
checks initially found that `actions/setup-python` implicitly required the
deleted conventional requirements file; the task escalated from Standard to
High-risk to repair and independently review that required-check contract. PR
review, merge SHA, and post-merge state remain to be recorded. Elapsed
implementation time before the CI correction was approximately 25 minutes,
context use approximately 14k tokens, and two bounded correction cycles have
been used. Production
research recovery is not claimed.
