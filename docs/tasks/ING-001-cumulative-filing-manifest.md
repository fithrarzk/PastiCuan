# ING-001: Cumulative filing identity and manifest merge

- Status: review
- Priority: P0
- Owner/model: Luna implementation from Sol design; Sol independent review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, `.agents/skills/tdd/{SKILL,tests}.md`, this card, `docs/specs/ingestion-contract.md`, `docs/runbooks/backfill.md`, and exact owned files; maximum 18k tokens
- Retry ceiling: three bounded red-green-refactor cycles; semantic conflicts are not retryable
- Escalation condition: changed provenance for an exact identity, unexplained restatement regression, requested removal/supersession, malformed baseline, or rolling-branch merge conflict
- Parallelism: one Luna writer and one root integration owner; later read-only reviewers only
- Base SHA: `491e5154690ab7d2e78c81239140d92a66b6613a`
- Branch: `feat/ING-001-cumulative-filing-manifest`
- Worktree: `../PastiCuan-wt/ing-001-cumulative-filing-manifest`
- Depends on: CI-002
- File ownership: `data/filing_manifest.py` (new), `scripts/ci/validate_manifest.py`, `.github/workflows/idx-filings.yml`, `tests/test_filing_manifest.py` (new), `docs/architecture/data-lifecycle.md`, `docs/reference/command-data-dictionary.md`, `docs/runbooks/backfill.md`, this task card, and `docs/tasks/CLAIMS.md` (root orchestrator only)
- Merge policy: autonomous

## Outcome

Merge each discovery draft into the rolling branch's reviewed filing manifest by stable filing identity, preserving every reviewed historical entry and failing closed on duplicate, regression, removal, or provenance conflict.

## Non-goals

- Import artifacts, add a durable ledger, make ingestion runtime-resumable, shard work, or change a database/schema/repository/publication contract.
- Automatically approve official data, invent missing 2023–2025 filings, or implement removal/supersession records.
- Edit the reviewed `data/idx_filing_manifest.json` as part of this code task.

## Current evidence

Discovery currently returns only rows observed in one run, and the IDX workflow copies that draft over the rolling reviewed manifest. The accepted ingestion contract requires cumulative history by stable identity. Existing reviewed data includes annual 2021–2022 and current 2026 entries; filling the official historical gaps remains ING-005.

## Invariants

- Exact identity is normalized `(ticker, filing_type, period_end, restatement_version)`; URL, publication timestamp, audit status, and checksum are provenance.
- Preserve all baseline rows and all historical restatement versions unchanged. Ordinary discovery never removes or silently rewrites reviewed evidence.
- `restatement_version` is a required positive integer. A lower newly introduced version for an existing base identity is a regression.
- A discovery draft and reviewed manifest remain review inputs, not accepted or bot-readable production evidence. Never synthesize `available_at`.
- Output ordering and diagnostics are deterministic. Conflicts exit before writing.

## Implementation contract

Add a small `data.filing_manifest` public seam for exact/base identity, merge, and an atomic CLI taking `--baseline`, `--discovered`, and `--output`. Validate inputs independently, reject duplicate exact identities, preserve identical rows idempotently, reject changed provenance at an exact identity, append only non-regressing new identities, and retain the latest draft diagnostics as run metadata rather than cumulative coverage. Update the validator to compare exact identities without collapsing restatement versions. In the workflow, update/check out the rolling review branch before invoking the merge; remove direct draft replacement. Use no network calls or production credentials in tests.

## Acceptance tests

- Duplicate exact identities in either input fail; repeated identical discovery is idempotent.
- A synthetic reviewed 2021–2026 history survives a narrow 2026 draft with no removals.
- Deletion/replacement fails; retaining v1 while appending v2 passes; introducing an older version fails.
- Same exact identity with changed URL, timestamp, or audit status fails.
- Baseline publication timestamps remain unchanged; no `available_at` is created; serialization/order is deterministic.
- The real reviewed manifest validates and self-merges without identity loss.
- Workflow tests prove rolling-branch checkout precedes cumulative merge and direct `cp` replacement is absent.
- Focused tests, workflow/YAML validation, full repository verification, and `git diff --check` pass.

## Rollout and rollback

Roll out through the reviewed code PR; do not dispatch discovery or change reviewed official entries in this task. Roll back with a normal code/workflow/docs revert. Never delete reviewed manifest additions or accepted evidence. A semantic conflict leaves the branch unchanged and requires reviewed correction or a future explicit supersession record.

## Handoff

Record commits, exact files, focused/full commands and results, independent reviews, PR/current-head checks, merge/post-merge evidence, limitations, and the next dependency-ready task.
