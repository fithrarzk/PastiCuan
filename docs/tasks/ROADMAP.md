# Autonomous Reliability and Research Roadmap

This roadmap is the dependency graph for agent-owned delivery. Priorities reflect production risk, not feature visibility. Each ID becomes a one-page task card before implementation.

## Current incident baseline

Observed on 2026-08-22 from `origin/main` at `f5166c7` and GitHub Actions runs through 2026-08-21. Treat these as incident evidence, not permanent architecture constants.

- The bot is correctly fail-closed because the last active scan is stale.
- Filing imports repeatedly reached the 30-minute limit; current ingestion re-downloads and reparses accepted rows.
- Reviewed filing discovery replaces history instead of accumulating it.
- Production has 45/45 quant-eligible issuers but only 32/45 verified profiles and 24/45 Business Scores; publication requires 45 and at least 41.
- A bot-created manifest PR can miss CI because pushes made with `GITHUB_TOKEN` do not trigger another workflow.
- Quant publication can precede scan failure, so active evidence is not an atomic pair.
- Railway deployment is not verifiably tied to every merged main SHA.
- Historical validation is not yet point-in-time safe and must remain `SHADOW`.
- Prior failures include non-finite JSON serialization, insufficient `schema_migrations` privilege, and expected fail-closed publication exits being reported too generically.

## Execution waves

Current delivery and incident state is summarized in the [2026-08-24 program handoff](../status/2026-08-24-program-handoff.md). Work is paused after verified ING-002; ING-003 is ready but unclaimed. Production recovery remains open because migration 007 is unapplied, ingestion is not yet skip-before-download resumable, and recent research refreshes failed closed.

Delivery-process work is tracked separately from the production dependency
graph: DOC-004 introduced risk-tiered execution lanes as `93d3086`; CI-003 is
active to remove duplicate PR testing and irrelevant production refresh
triggers. Neither task claims research recovery or changes the ING-003
dependency order.

| Wave | Objective | Exit condition |
|---|---|---|
| 0 | Agent contract and trustworthy delivery controls | Docs merged; GitHub identity/rules audited; PR checks trigger reliably |
| 1 | Restore cumulative, resumable official evidence | Full reviewed history imports without repeated work; readiness is diagnostic |
| 2 | Atomic publication and production recovery | One active release pair; Railway exact-SHA deploy and last-good recovery |
| 3 | Point-in-time data integrity | Versioned evidence and historical queries prove no look-ahead |
| 4 | Statistically defensible analytics | Frozen model cards and genuine out-of-sample validation |
| 5 | Product consistency, performance, and operating maturity | Commands agree, SLOs observed, restore drill proven |

## Wave 0 — Context and delivery bootstrap

| ID | Task | Owner/model | Depends | Merge | Acceptance |
|---|---|---|---|---|---|
| DOC-001 | Domain glossary, agent contract, autonomy, worktrees, handoffs, core specs, roadmap | Sol design + Luna edits | none | autonomous | Docs are internally linked; `CONTEXT.md` remains glossary-only; agent rules define done and safety |
| OPS-001 | Audit GitHub auth, ruleset, Actions permissions, environments, secrets-by-name, auto-merge, Railway linkage | Sol | DOC-001 | human-gated only for platform setting changes | Machine-readable inventory; invalid auth is one explicit bootstrap action; no secret values logged |
| CI-001 | Make bot-created PR validation reliable | Luna from Sol contract | OPS-001 | autonomous | A generated manifest PR receives all required current-head checks without recursion and can auto-merge when green |
| CI-002A | Restore a supported yfinance dependency chain | Luna | CI-001 | autonomous | Runtime requirements resolve on Python 3.12, public provider seams are characterized offline, and all dependency audits are clean without waivers |
| CI-002B | Decode SQL-ASCII migration identities at the storage boundary | Luna | CI-002A | autonomous | Repository migration IDs are exact strings for text/bytes, invalid encoding fails, and the strict SQL-ASCII gate passes without output repair |
| CI-002 | Establish required PR gates | Luna | CI-001, CI-002A, CI-002B | autonomous | `unit`, `quality`, `workflow-policy`, `migration`, `container-smoke`, conditional `manifest-validate`, and `security` are green and required |
| DOC-002 | Add architecture maps, command/data dictionary, formula/model-card index, and incident/deploy/backfill runbooks | Luna | DOC-001 | autonomous | A new agent can locate source of truth, owner, invariant, test, and runbook without reading chat history |
| REG-001 | Lock prior production failures into regression tests and error taxonomy | Luna | CI-002 | autonomous | Tests cover NaN sanitization, migration privilege preflight, and distinct WAITING/UNAVAILABLE/policy-gate/infrastructure exits with actionable summaries |

## Wave 1 — Official evidence recovery

Tasks touching `operations/research_cli.py`, `storage/repository.py`, or migrations are serialized under one integration owner.

| ID | Task | Owner/model | Depends | Merge | Acceptance |
|---|---|---|---|---|---|
| ING-001 | Cumulative filing identity and manifest merge | Sol design, Luna implementation | CI-002 | autonomous | Reviewed 2021–2026 entries cannot disappear; duplicate/regression/removal tests pass |
| ING-002 | Durable filing-work ledger migration and repository API | Sol schema, Luna implementation | ING-001 | autonomous with migration gates | States, leases, attempts, errors, checksums, and artifact IDs persist transactionally |
| ING-003 | Skip-before-download resumable importer | Luna | ING-002 | autonomous | Interrupted run resumes; a rerun of any fully accepted reviewed manifest performs zero downloads; bad row does not roll back good rows |
| ING-004 | Deterministic shards, bounded retry, and progress aggregation | Luna | ING-003 | autonomous | No shard approaches timeout; durable totals include accepted/skipped/quarantined/retryable/remaining |
| OBS-001 | Per-issuer readiness diagnostics | Luna | ING-002 | autonomous | Exact unverified/unscored tickers, missing concepts/history, gates, sources, and checksums appear in CLI and job summary |
| ING-005 | Reconcile reviewed annual history plus current interim filings and complete import | Orchestrator | ING-004, OBS-001 | data-reviewed | Required annual years and current interim period are cumulative; 45 verified profiles, at least 41 Business Scores, 45 quant eligible; explicit waivers only where reviewed |
| OPS-002 | Serialize import and research orchestration | Sol design, Luna workflow | ING-004 | autonomous | Manifest validation -> import -> readiness -> one research refresh; all production DB writers share a lock |

## Wave 2 — Atomic publication and deployment

| ID | Task | Owner/model | Depends | Merge | Acceptance |
|---|---|---|---|---|---|
| REL-001 | Append-only release-activation schema | Sol | ING-005 | autonomous with migration gates | One release activation pairs a formula research release with quant and scan candidates; injected mid-build failure changes neither active ID |
| REL-002 | Resolve every bot research command through active release | Luna | REL-001 | autonomous | `/scan`, `/range`, `/decision`, `/quant`, `/status` report one release pair and structured unavailability |
| DEP-001 | Exact-SHA Railway deployment check | Luna from Sol contract | CI-002 | autonomous | Every deployable main SHA reports Railway status and checks `/`, `/ready`, signature, and snapshot readability |
| DEP-002 | Last-good code and research recovery | Sol design, Luna implementation | REL-001, DEP-001 | autonomous | Redeploy recorded healthy artifact or append prior release activation; no SQL down rollback |
| OPS-003 | Production end-to-end smoke and incident lifecycle | Luna | REL-002, DEP-002 | autonomous | `/scan`, `/status`, `/evidence BBRI`, `/fund BBRI`, `/range BBRI`, `/chart BBRI`, `/portfolio BBRI BBCA` agree; one incident issue closes on recovery |

## Wave 3 — Point-in-time integrity

| ID | Task | Owner/model | Depends | Merge | Acceptance |
|---|---|---|---|---|---|
| PIT-001 | Version issuer profiles, sectors, shares, FX, policy rates, membership, and source facts | Sol schema + Luna implementation | REL-001 | research-reviewed | Every revision retains `available_at`; historical queries cannot observe later versions |
| PIT-002 | Validate XBRL dimensions, consolidation, declared period, and restatements | Sol semantics + Luna tests/code | PIT-001 | research-reviewed | Fixture corpus covers accepted, ambiguous, dimensional, wrong-period, and restated facts |
| PIT-003 | Official historical memberships and session calendar | Orchestrator/data review | PIT-001 | data-reviewed | Additions, removals, delistings, and membership periods are immutable and official; no expired seed dependency |
| PIT-004 | Historical OHLCV causality and corporate actions | Sol | PIT-001, PIT-003 | research-reviewed | Known-then availability, splits, dividends, rights, suspension, delisting, and missing-exit policies are explicit and tested |
| PIT-005 | Deterministic point-in-time audit fixture | Luna | PIT-002, PIT-004 | autonomous | Same immutable inputs rebuild the same monthly panel twice; revision tests distinguish known-then from known-now |

## Wave 4 — Analytics validation

| ID | Task | Owner/model | Depends | Merge | Acceptance |
|---|---|---|---|---|---|
| ANA-001 | Separate model cards for Business Score, quant factors, technical entry, valuation range, and portfolio | Sol | PIT-005 | research-reviewed | Each names exact digest, cohort, lag, benchmark, costs, missing-data policy, thresholds, and limits |
| ANA-002 | Freeze development/holdout protocol and model identity | Sol | ANA-001 | research-reviewed | Tested score matches model ID and code digest; holdout dates/spec are immutable before evaluation |
| ANA-003 | Purged walk-forward validation with dependence-aware uncertainty | Sol design + Luna implementation | ANA-002 | research-reviewed | Block bootstrap or HAC, multiple-testing control, fixed investable benchmark, attrition/delisting, and costs are tested |
| ANA-004 | Validate technical entry separately and rename false confidence | Sol + Luna | ANA-003 | research-reviewed | `data_coverage_confidence` replaces predictive wording unless calibrated; execution begins at an executable price |
| ANA-005 | Portfolio covariance, turnover, liquidity, and tail-risk validation | Sol | ANA-003 | research-reviewed | Out-of-sample comparison and explicit constraints outperform or reject the current fixed shrinkage policy |
| REL-003 | Immutable calculation provenance and promotion | Sol | ANA-003 | research-reviewed | Digest covers parsing, schema, formulas, validation, outcomes, operations, and locked dependencies; model ID reuse fails |

## Wave 5 — Product and operations maturity

| ID | Task | Owner/model | Depends | Merge | Acceptance |
|---|---|---|---|---|---|
| UX-001 | Structured stale/excluded/missing reasons and separate coverage labels | Luna | REL-002 | autonomous | Historical detail remains labeled; current ranking stays closed; market/quant/profile/business coverage are distinct |
| PERF-001 | Replace per-issuer N+1 factor reads with set-based cutoff query | Luna | PIT-001 | autonomous | One transaction/cutoff, measured query reduction, identical deterministic output |
| UX-002 | Align Telegram and Streamlit with immutable stored evidence | Luna | REL-002, PIT-004 | autonomous | Both surfaces report the same release/snapshot IDs and no hidden live calculation |
| OBS-002 | Stage telemetry and freshness SLO | Luna | OPS-003 | autonomous | Duration, counts, coverage, age, release/code/deploy IDs, failures, query count, and skip rate are visible; PRIMARY within agreed window |
| BAK-001 | Backup metadata and disposable restore drill | Luna | CI-002 | autonomous | Encrypted object checksum/schema/size recorded; periodic restore succeeds; pre-migration backup is mandatory |
| SEC-001 | Pin Actions and dependencies; split production roles | Sol review + Luna changes | CI-002 | platform-reviewed | Immutable action SHAs, hashed dependency lock, least-privilege ingest/publisher/migrator/Railway/R2 roles |

## Worktree allocation

Parallel work is limited by file ownership, not agent count:

- `wt-docs`: documentation only.
- `wt-ingest`: `data/idx_reports.py`, new ingestion modules/tests; integration owner alone touches `operations/research_cli.py` and relevant repository methods.
- `wt-observability`: new diagnostics module/tests and narrowly owned reporting adapters.
- `wt-cicd`: `.github/`, CI scripts, container smoke fixtures.
- Later `wt-pit-schema`, `wt-scan-ux`, `wt-performance`, `wt-validation`, and `wt-release` start only when predecessor contracts are merged.

Before starting a wave, record exact file ownership in task cards. Rebase each worktree on current `origin/main`; merge shared-contract PRs sequentially.

## Definition of program recovery

The current production incident is resolved only when a new signed `PRIMARY` scan uses a current completed session with 45/45 market and verified-profile coverage, at least 41/45 Business Scores, 45/45 quant eligibility, and matching active release IDs across bot commands. A green unit suite or merged PR alone is not recovery.
