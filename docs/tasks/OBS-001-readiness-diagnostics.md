# OBS-001: Per-issuer readiness diagnostics

- Status: claimed
- Priority: P0
- Owner/model: GPT-5 root writer; Sol independent Standards and Spec reviews
- Delivery lane: High-risk (point-in-time evidence/source diagnostics)
- Reasoning effort: high
- Context budget: `AGENTS.md`, `CONTEXT.md`, TDD/Supabase/Postgres skills, this card, `docs/specs/ingestion-contract.md`, `docs/runbooks/{stale-snapshot,refresh}.md`, and exact owned files; maximum 60k tokens
- Retry ceiling: three correction cycles
- Escalation: any schema/query/migration/grant, production access, changed readiness threshold, evidence eligibility, source policy, publication/release behavior, or unbounded/unredacted output
- Parallelism: one root writer; two fresh read-only reviewers only after the final exact head
- Base SHA: `d2acfbe4a6df6bda631fab577405ad3d8c0a1c8a`
- Branch/worktree: `feat/OBS-001-readiness-diagnostics` / `../PastiCuan-wt/obs-001-readiness-diagnostics`
- Issue: #48
- Depends on: verified ING-002 and merged/documented ING-004 (`d2acfbe`)
- File ownership: `analysis/factor_dataset.py`, `operations/research_cli.py`, `tests/test_readiness_diagnostics.py`, `tests/test_research_automation.py`, `docs/architecture/data-lifecycle.md`, `docs/reference/command-data-dictionary.md`, `docs/runbooks/{stale-snapshot,refresh}.md`, this card, and `docs/tasks/CLAIMS.md`
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

1. `analysis.factor_dataset` derives a diagnostic-only sorted list of absent
   semantic concept groups from facts already selected by `available_at`. The
   profile-specific concept set is used only when the Issuer profile is verified;
   an unverified profile is disclosed instead of guessing an accounting model.
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
  `available_at`; no database SQL is added or changed.

## Verification and handoff

Develop red-green-refactor with focused tests, then run the complete High-risk
verification from `AGENTS.md`, release/workflow/security/YAML/Ruff/mypy checks,
and fresh Standards/Spec reviews on the exact final head. Handoff records exact
SHAs, files, behavior, commands/results, PR/check/review/merge/post-merge state,
Supabase evidence or `not applicable`, limitations/rollback, elapsed/context,
correction cycles, and ING-005 as the next task unlocked by OBS-001.

