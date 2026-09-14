# OBS-001: Per-issuer readiness diagnostics

- Status: review
- Priority: P0
- Owner/model: GPT-5 ticket agent; Sol independent Standards and Spec reviews
- Delivery lane: High-risk (point-in-time evidence/source diagnostics)
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, TDD/Supabase/Postgres skills, this card, `docs/specs/ingestion-contract.md`, `docs/runbooks/{stale-snapshot,refresh}.md`, and exact owned files; maximum 60k tokens
- Retry ceiling: three correction cycles
- Escalation: any schema/migration/grant or write query, production access, changed readiness threshold, evidence eligibility, source policy, publication/release behavior, or unbounded/unredacted output
- Parallelism: one ticket agent; two fresh read-only reviewers only after the final exact head
- Base SHA: `02475e6f8d6a712d883ef49ec4415639c1609012`
- Branch/worktree: `feat/OBS-001-readiness-diagnostics` / `../PastiCuan-wt/obs-001-readiness-diagnostics`
- Issue: #48
- Depends on: verified ING-002 and merged/documented ING-004 (`d2acfbe`);
  rebased after the ticket-ownership contract merged as `02475e6`
- File ownership: `storage/repository.py`, `operations/{readiness_diagnostics,research_cli}.py`, `tests/test_readiness_diagnostics.py`, `tests/test_research_automation.py`, `docs/architecture/data-lifecycle.md`, `docs/reference/command-data-dictionary.md`, `docs/runbooks/{stale-snapshot,refresh}.md`, this card, and `docs/tasks/CLAIMS.md`
- Merge policy: autonomous squash merge only after complete local verification, fresh independent zero-finding reviews on the final exact head, and all required current-head checks

## Outcome and boundary

Expose deterministic, bounded per-issuer diagnostics from the same point-in-time
factor inputs and candidate snapshot used by existing readiness gates. Report
exact unverified, Business-Score-unscored, and quant-ineligible tickers; each
issuer's existing gate results; unavailable normalized concept groups and annual
history; official source identities; and evidence checksums in CLI output and the
daily research job report/summary.

This task is diagnostic only. It does not change the 45-member, 90% quant,
profile, Business Score, freshness, source, coverage, publication, risk, release,
or promotion gates. It adds no provider fallback, Yahoo fundamental, future-known
evidence, schema, production query, migration, dispatch, publication, holdout
optimization, model change, or Railway deployment claim.

## Accepted design

1. One set-based, read-only repository query inventories constituent profile,
   normalized concept, period, official source, and checksum fields using the
   same membership date and `available_at <= as_of` plus non-quarantine rules as
   factor evidence. Operations code derives a diagnostic-only sorted list of
   absent semantic concept groups. Profile-specific requirements are used only
   for a verified Issuer profile; an unverified profile is disclosed instead of
   guessing an accounting model. No calculation-path file changes.
2. `candidate_readiness` keeps every current boolean and threshold unchanged and
   adds sorted top-level blocker ticker lists plus one ticker-sorted diagnostic
   row per constituent. Rows expose existing gates, annual-history count/target,
   financial periods, source URLs, document/profile checksums, missing concept
   groups, and a stable concept-diagnostic status. Missing ranking rows remain
   explicit. Values are normalized from candidate JSON/CSV seams and raw provider
   bodies or exception text are never included.
3. A new inspection CLI prints strict JSON for both ready and rejected candidates
   and exits nonzero when existing readiness fails. Existing `check-candidate`
   validation semantics remain unchanged.
4. `run-daily-research` stores the same readiness object in the quant stage before
   raising the existing `QUANT_READINESS_REJECTED` outcome. The unchanged workflow
   already renders the persisted report into `GITHUB_STEP_SUMMARY`; no workflow or
   publication path changes.

## TDD acceptance

- Complete, missing, unverified, and conflicting/malformed diagnostic fields are
  deterministic, strictly JSON-safe, ticker-sorted, and bounded to constituents.
- Known general and bank facts produce exact missing semantic groups; unverified
  profiles do not receive a guessed profile-specific concept requirement.
- Top-level blocker ticker lists exactly match per-issuer existing gates, including
  absent ranking rows, while `ready` and all current aggregate checks/counts remain
  byte-for-byte equivalent for the same candidate.
- CLI inspection emits the full diagnostic report on success and failure with the
  existing non-ready exit convention; `check-candidate` continues to reject.
- A daily readiness rejection writes diagnostics into the job report and recorded
  metrics/summary without publishing quant or scan evidence.
- Point-in-time tests prove later facts cannot enter diagnostics before
  `available_at`; the new SQL is read-only, set-based, parameterized, and covered
  on a disposable database. No schema or write query is added or changed.

## Implementation evidence — 2026-09-13

- Red/green slices cover profile-specific semantic concept groups, unverified
  profile refusal, one shared cutoff for profile/Filing/fact evidence, candidate
  evidence attachment, exact blocker lists, missing rankings, malformed/redacted
  fields, inspection CLI failure output, and persisted daily rejection metrics.
- Focused readiness/research/candidate tests passed 27 tests with one disposable
  test skipped; the disposable PostgreSQL 14 run exercised that case and returned
  `verified 8 migrations`. Complete Python 3.12 verification passed compilation
  and 197 tests (`OK`, four disposable tests skipped and separately exercised),
  research-release validation, workflow policy, tracked-source security, Ruff,
  CI-configured mypy for three changed source files, all workflow YAML, and diff
  checks.
- Release validation against `origin/main` preserved calculation revision 2,
  formula/model identity, and digest
  `188c66c3df19bb92d0ba934b4886112752159f1a7eb7b3fb165ee036670765e3` with
  `calculation_changed: false`. CI-configured mypy passed three source files on
  Python 3.12; Ruff and diff checks passed.
- Supabase/Postgres guidance shaped the set-based, parameterized, index-aligned
  read with no locks or network work inside a transaction. No Supabase MCP or
  production query/mutation was performed; production evidence is not applicable.
- Correction cycles: two. An initial diagnostic calculation-path design was
  discarded before commit when release validation showed that a diagnostic task
  must keep frozen model code byte-identical. The replacement uses storage plus
  operations metadata only. Fresh Spec review then identified silently accepted
  malformed annual-history metadata; the red/green fix now records a `history`
  diagnostic error and keeps the readiness output fail-closed.
- Final exact-head reviews, PR/CI/merge/cleanup, post-merge verification, and the
  dated handoff remain pending.

## Verification commands

```bash
python -m compileall -q analysis data storage operations telegram_utils bot.py bot_webhook.py
python -m unittest discover -s tests -v
python -m operations.research_cli check-research-release --base-ref origin/main
python scripts/ci/check_workflow_policy.py
python scripts/ci/check_security.py
ruff format --check operations/readiness_diagnostics.py operations/research_cli.py storage/repository.py tests/test_readiness_diagnostics.py tests/test_research_automation.py
ruff check operations/readiness_diagnostics.py operations/research_cli.py storage/repository.py tests/test_readiness_diagnostics.py tests/test_research_automation.py
mypy --follow-imports=skip --ignore-missing-imports --disable-error-code=import-untyped -- operations/readiness_diagnostics.py operations/research_cli.py storage/repository.py
git diff --check
```

The disposable command used `scripts/ci/check_migrations.py` with a task-scoped
loopback connection variable, `--base-ref origin/main`, and
`--verify-disposable-down-reup`; it returned exactly `verified 8 migrations`.

## Limitations and rollback

Diagnostics describe only evidence known by `as_of`; they do not repair missing
evidence or authorize publication. Production remains blocked by unapplied
migrations 007/008 and their protected rollout. Roll back with a reviewed
code/documentation revert or forward fix; retain every accepted/quarantined
artifact and published snapshot, never run a production down migration, and keep
the last good snapshot active on any diagnostic failure.

## Verification and handoff

Develop red-green-refactor with focused tests, then run the complete High-risk
verification from `AGENTS.md`, release/workflow/security/YAML/Ruff/mypy checks,
and fresh Standards/Spec reviews on the exact final head. Handoff records exact
SHAs, files, behavior, commands/results, PR/check/review/merge/post-merge state,
Supabase evidence or `not applicable`, limitations/rollback, elapsed/context,
correction cycles, and ING-005 as the next task unlocked by OBS-001.
