# Program handoff — 2026-08-24

This is the shutdown-safe execution handoff after ING-002. Production truth is `origin/main` at `25c6f2e691e8757b54c76787fe57ff0d5da0f629`; local `main`, candidate artifacts, and cached bot state are not production evidence.

## Verified delivery

| Task | Outcome | Merge and verification |
|---|---|---|
| DOC-001 | Domain glossary, agent contract, autonomy, worktree, handoff, and roadmap foundations | `b9f889e` |
| OPS-001 | Read-only GitHub/automation inventory | Verified audit; no platform mutation |
| CI-001 | Generated manifest PR validation reaches the exact pushed head | `693af47`; exact-head run `32523578280`; intentional mismatch proof `32523704901` |
| CI-002A | Supported Python 3.12/yfinance dependency chain | PR #19, `a60a561` |
| CI-002B | Exact SQL-ASCII migration identity decoding | PR #21, `6484912` |
| CI-002 | Eight required PR gates and strict branch rules | PR #22, `8840930`; ruleset `20977060`; merge verification `32563023464` |
| DOC-002 | Architecture, lifecycle, reference, model index, and operations runbooks | PR #23, `491e515`; merge verification `32563543541` |
| ING-001 | Cumulative, deterministic reviewed Filing manifest merge | PR #26, `5d8817f`; 133 tests; merge verification `32565707918` |
| REG-001 | Stable redacted research outcomes, strict JSON, and migration-ledger preflight | PR #27, `6429643`; 147 tests; merge verification `32566667756` |
| ING-002 | Durable Filing work/attempt ledger migration and fenced repository API | PR #29, `25c6f2e`; 156 tests; PostgreSQL 16 UTF-8 and SQL-ASCII verification; all eight PR checks; merge verification `32571008743` |

Independent Standards and Spec reviews reported zero findings on the final ING-001 and REG-001 heads and on ING-002 final PR head `3083e7b`. No reviewed manifest, formula, publication threshold, accepted evidence, secret, or production schema was changed by the documentation/CI work.

## Still unavailable or unsafe to claim

- Production research is not recovered. Merge-triggered refresh runs `32565707917`, `32566667730`, and `32571008822` failed closed at refresh/publish. The last accepted production scan remains stale unless newer accepted Supabase evidence proves otherwise.
- Scheduled `idx-filings` run `32685938136` failed closed on 2026-08-24 while opening its review PR because discovered JPFA Q2 2026 provenance conflicted with the reviewed identity. Resolve that conflict through official evidence review; never overwrite the accepted manifest identity to make discovery pass.
- Migration `007_filing_work_ledger` is merged but **not applied in production**. Applying it requires a verified backup, reviewed rollout declaration, protected migrator, and read-only post-apply evidence. Never run its down migration in production.
- ING-003 is designed but not implemented. Therefore ingestion is not yet skip-before-download resumable, and a rerun is not proven to perform zero downloads for accepted work.
- ING-004 sharding/retry/progress aggregation, OBS-001 readiness diagnostics, and ING-005 reviewed evidence completion remain open. The incident baseline of 32/45 verified profiles and 24/45 Business Scores has not been superseded by accepted evidence.
- Quant and scan publication are not an atomic release pair; REL-001 remains open.
- Railway exact-main-SHA deployment verification and last-good deployment recovery remain open (DEP-001/DEP-002).
- Point-in-time expansion and analytics validation remain `SHADOW` roadmap work. No model promotion is authorized.

## Next task: ING-003

ING-003 is ready for an isolated worktree from `origin/main`, but must remain unclaimed until work resumes. Its task card is [ING-003 skip-before-download](../tasks/ING-003-skip-before-download.md).

The required ordering is:

1. Confirm issue/claim state and current `origin/main`.
2. Implement preflight and complete-manifest sync before provider access.
3. Skip exact `ACCEPTED` and terminal `QUARANTINED` work before claim/download.
4. Claim unfinished work with migration-007 fenced leases.
5. Commit accepted or quarantined artifact, facts/profile outcome, ledger item, and attempt per Filing; one bad row cannot roll back a prior accepted row.
6. Keep production dispatch blocked until migration 007 rollout evidence exists.

After ING-003, stop and update this handoff before starting ING-004, per owner direction.

## Workspace and shutdown notes

- The shared local `main` checkout is clean at user-owned merge commit `9627336`, two local commits ahead of `origin/main`. User commit `0518e21` tracks `PROMPT-ORCHES.md` and a `storage/repository.py` change; the orchestrator did not create, rewrite, push, or include either commit in this documentation branch.
- A fast audit found no secret or hidden code delta in those two commits, but `PROMPT-ORCHES.md` still directs reimplementation of verified CI-002/DOC-002 and says it must not be committed. Do not push the commits as-is; update/archive that prompt explicitly first.
- All completed task worktrees and remote task branches through ING-002 were removed. Temporary verification environments and disposable PostgreSQL clusters were stopped and moved to Trash.
- GitHub issues #25, #28, and their task branches are closed/released. PRs #27 and #29 are merged.
- It is safe to stop the agent/laptop: no production workflow, database migration, deployment, or background monitor is required to complete the recorded state.

## Resume checklist

```bash
git status --short
git branch --show-current
git fetch origin
git merge-base HEAD origin/main
git log -5 --oneline origin/main
```

Then read `AGENTS.md`, `CONTEXT.md`, this handoff, `docs/tasks/CLAIMS.md`, and the ING-003 card. Preserve the shared-checkout user changes and create `../PastiCuan-wt/ing-003-resumable-importer` from current `origin/main`.
