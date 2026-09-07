# UX-003: Telegram-only delivery

- Status: review
- Priority: P1
- Owner/model: root orchestrator (GPT-6) with independent Sol/high Standards and Spec review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests,mocking}.md`, this card, `docs/agents/delivery-lanes.md`, `docs/architecture/system-map.md`, `docs/specs/ci-cd-contract.md`, `DEPLOY_FREE.md`, and exact owned files; target 30k tokens, High-risk-lane maximum 60k
- Retry ceiling: three original cycles plus one owner-authorized recovery cycle (2026-09-07), limited to retained workflow cache inputs, regression coverage, and review records
- Escalation condition: any required change to Telegram webhook/runtime behavior, a production workflow, evidence/research semantics, migration/schema/grants, credentials, or publication gates
- Parallelism: one root writer; two fresh read-only reviewers after implementation
- Base SHA: `26d45080689fb1d96f874ccec65532ec5789f13c` (original implementation base `1f5651d33bc2d41ffe99b1c8aad0515e7b3360b5`; merged DOC-005 without rewriting history)
- Branch: `refactor/UX-003-telegram-only`
- Worktree: `../PastiCuan-wt/ux-003-telegram-only`
- Depends on: none
- File ownership: `.dockerignore`, `.env.example`, `.github/workflows/{ci,validate-branch}.yml`, `.gitignore`, `.streamlit/config.toml`, `DEPLOY_FREE.md`, `README.md`, `app.py`, `analysis/{contracts,engine,presentation,scanner}.py`, `requirements.txt`, `scripts/ci/check_dependencies.sh`, `tests/test_ci_gates.py`, `tests/test_reliability.py`, `tests/test_yfinance_compat.py`, `ui/**`, `docs/architecture/system-map.md`, `docs/tasks/ROADMAP.md`, `docs/tasks/CLAIMS.md`, and this card
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
- `rg` finds no active Streamlit runtime/deployment references outside historical task records. Legacy comments/docstrings in the four unchanged analysis modules are retained to preserve the research release identity, per owner direction.
- Required CI is green on the current PR head.
- Both ordinary and exact-head validation workflows use explicit existing files for every enabled pip cache.

## Rollout and rollback

The merge removes the unneeded Streamlit deployment surface. Railway may rebuild the unchanged Telegram container from `main`. Existing path filters will dispatch `research-daily` for this removal; verify its outcome without changing refresh triggers or publication gates. Exact-SHA Railway proof remains DEP-001. Roll back with a normal revert if the deleted standalone interface is required again.

### Authorized recovery scope

The owner authorized one additional bounded recovery cycle after fresh review
found five implicit pip caches in four retained production workflows. Root owns
`.github/workflows/{research-daily,backup,research-validation,idx-filings}.yml`
for cache-input changes only, plus `tests/test_ci_gates.py`, this card,
`docs/tasks/CLAIMS.md`, and the dated program handoff. The regression seam is
the setup-python cache configuration consumed by all retained workflows:
every pip cache must name existing dependency profiles and include transitive
bot requirements for jobs. No trigger, permission, timeout,
production command, schema, or research behavior change is authorized here.
The expanded workflow-policy check additionally requires immutable action pins
and per-workflow non-cancelling concurrency for backup and validation. These
prerequisites are included in this recovery; they do not serialize all writers
across workflows (OPS-002 remains open).

## Handoff

Implementation from base `1f5651d` deletes the Streamlit entry point,
package, configuration, and dependency profile while retaining Telegram polling,
webhook, container, and provider compatibility. The red delivery-surface test
failed on `app.py`; after removal, 22 focused tests passed. A clean Python 3.12
environment passed compilation, all 161 tests, research-release integrity,
strict audits of all three retained dependency profiles, Ruff, shell syntax,
and `git diff --check`. The initial local full-suite failure was diagnosed as
the pre-existing developer environment having yfinance 1.2.0 instead of the
retained 1.5.2 pin; the clean pinned environment passed. No production action,
formula/release change, migration, or credential use occurred. Initial PR
required checks found that `actions/setup-python` implicitly required the
deleted conventional requirements file; the task escalated from Standard to
High-risk to repair and independently review that required-check contract. PR
review, merge SHA, and post-merge state remain to be recorded. Fresh Sol/high
Standards review reported one medium record-provenance finding and zero code
smells; fresh Sol/high Spec review reported one medium delivery-state finding
and no implementation or scope findings. This update records the review
provenance; pushing the corrected head and obtaining green required checks
resolves the remaining finding. Elapsed implementation time before the CI
correction was approximately 25 minutes, context use approximately 18k tokens,
and two bounded correction cycles have been used. Production research recovery
is not claimed.

### Final bounded correction — 2026-09-07

Resumed PR #38 at `60fff5057e182267a133cdc21dc2543561b2c898` and
merged `26d4508` without force-pushing; DOC-005 policy is intact. The exact-head
quality job `101542469934` in run `34054004575` reported Ruff formatting failures
in two analysis modules and `tests/test_{ci_gates,reliability}.py`. Restored all
four nonessential analysis comment/docstring edits to main and formatted only
the two flagged test files. No formula or research release revision changed.

The third and final correction cycle is consumed. Python 3.12.9 with the retained
pinned runtime passed all 161 tests in 6.675 seconds, compilation, and release
identity generation. Ruff 0.12.11 formatting/lint, workflow policy (two
workflows), shell syntax, and whitespace checks passed. A mypy cache-writing
internal error in the runtime environment disappeared with cache disabled;
the CI-only dependency environment is checked separately. Permissions,
concurrency, timeouts, and exact-head guard remain unchanged; explicit cache
inputs name retained profiles. Full-suite failure-path tests cover workflow
policy rejection, head mismatch, dependency audit failure, and container cleanup.

Final committed-head release policy, independent reviews, remote checks, merge,
and post-merge verification remain pending. Stop with a recoverable handoff if
this correction does not resolve required checks. No Supabase access or
production writes occurred. Exact-SHA Railway deployment remains DEP-001 work.

### Owner-authorized review recovery — 2026-09-07

The usage-limit interruption was resolved. Fresh reviews of `a84766e` found
one Standards provenance mismatch and two Spec findings: implicit cache inputs
would break retained production workflows, and the no-refresh rollout claim
was incorrect. Owner authorized the additional recovery cycle. The cache test
failed at `research-daily.yml:refresh` before the fix and passed after all five
retained production setup steps named jobs and transitive bot requirements.
The test also inventories every enabled pip cache and checks that inputs exist.
Claim provenance and rollout wording are reconciled. Existing refresh triggers,
commands, permissions, timeouts, and pre-existing concurrency settings are
unchanged. Backup and validation gain separate non-cancelling concurrency
groups and immutable same-major action pins to pass required workflow policy.

Pinned Python 3.12 verification passed compilation and all 161 tests in 10.258s;
Ruff formatting/lint, CI-only mypy (three source files), shell syntax, and
whitespace checks passed. No production or Supabase calls were made. Fresh
final-head independent review and remote checks remain required before merge.
Recovery cycle: one of one authorized; GPT-6 root, Sol/high reviewers.
