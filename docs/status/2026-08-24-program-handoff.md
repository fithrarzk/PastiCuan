# Program handoff — 2026-08-24

Updated 2026-09-13 after verified ING-004. Production code is `origin/main`
at `9aeb54f9ab526a4c4ab4c514ae76b5bf6a76aa22`; accepted Supabase evidence
and signed published snapshots remain production research truth.

## Current checkpoint — 2026-09-13

- ING-004 (High-risk, GPT-5 root writer with independent Sol/high Standards and
  Spec reviewers) merged through PR #46 as `9aeb54f`, from base `6b66f65` and
  reviewed final head `d2348493b7f6a9e4bcae57cd7f0166e94cbc1149`.
  Deterministic ticker/reporting-year shards now share one immutable validated
  retry/budget policy, cap durable allowlisted attempts, preserve interruption
  progress, and aggregate cross-shard counts from the filing-work ledger before
  research refresh. Accepted and terminal quarantined Filings remain skipped
  before claim/download.
- Changed files: `.github/workflows/idx-filings.yml`,
  `data/{filing_work_policy,idx_filing_importer}.py`,
  `storage/repository.py`, `operations/research_cli.py`, workflow-policy code,
  five test modules, ingestion architecture/reference/backfill documentation,
  the task card, and claim record. The implementation branch and worktree were
  removed after merge; issue #45 is closed, its claim label is released, and the
  remote branch is deleted.
- Local final-head evidence: compilation passed; 188 tests passed with three
  disposable tests skipped there and exercised separately; release validation,
  workflow policy, tracked-source security, YAML, Ruff, CI-configured mypy, and
  diff checks passed. Clean UTF-8 and SQL-ASCII disposable PostgreSQL databases
  each returned `verified 8 migrations`. The reviewed 124-Filing manifest
  distributes `17/16/13/17/19/15/16/11`; the largest shard's 570-second serial
  acquisition boundary remains inside the 1,200-second application budget and
  45-minute job timeout.
- Fresh Standards and Spec reviews on exact head `d2348493` both passed with
  zero findings. All eight applicable current-head PR checks passed in run
  `34710446087`. Squash merge and branch deletion are verified. Exact-merge main
  run `34710537290` passed compilation, release validation, and the full suite.
- Exact-merge research run `34710537324` failed closed at preflight with exit 40,
  `REQUIRED_MIGRATION_MISSING` for migrations 007 and 008. No research was
  published. Neither migration was applied, no Supabase MCP/production query or
  mutation occurred, and exact-SHA Railway deployment remains unproven.
  Supabase evidence was limited to a current changelog review with no applicable
  breaking database/pooling change; production evidence is therefore not
  applicable for this code/workflow delivery.
- Limitations and rollback: production ingestion remains blocked until explicit
  rollout authorization, verified backup, protected migrator, compatibility and
  grant proof, session-compatible writer, and read-only post-apply verification.
  Roll back only by reviewed code/workflow revert or forward fix while retaining
  ledger/evidence history; never run production down migrations. Research stays
  SHADOW unless exact-digest evidence passes every gate.
- Delivery took approximately 12 hours wall-clock including the continuation
  pause, about 50k context tokens, and three correction cycles: workflow
  permission policy, shared retry/import-policy consolidation after review, and
  a final falsey-policy boundary fix. Next dependency-ready task is OBS-001;
  ING-005 remains blocked on both ING-004 and OBS-001 completion evidence.

The September 8 and earlier sections below are historical; this checkpoint
supersedes their present-tense delivery and next-task statements.

## Current checkpoint — 2026-09-08

- ING-003 merged via PR #43 as `6a50ae4`, from base `1b7e06e` and reviewed
  head `c99c4bac60356d418205b449ad9acfe111cbb2c2`. Imports now skip accepted
  and terminal quarantined filings before download, batch atomic manifest
  synchronization, fence downloads, commit each Filing independently, and
  return structured outcomes. Additive migration 008 preserves checksum
  mismatch artifacts as terminal quarantine; migration 007 is unchanged.
- Standards and Spec each passed with zero findings. Eight PR checks passed
  in `34196294226`; main verification `34196669570` passed. Local evidence:
  175 tests, two disposable tests exercised separately; UTF-8/SQL-ASCII each
  verified eight migrations. The 100-Filing regression reduced prepare calls
  from 302 to at most six and proves conflict rollback. See the
  [task record](../tasks/ING-003-skip-before-download.md) for commands and history.
- Research run `34196669534` failed closed at preflight, exit 40,
  `REQUIRED_MIGRATION_MISSING` for 007 and 008. Production import and research
  recovery remain blocked on protected rollout, backup, session-compatible
  writer and read-only verification. No production mutation/MCP query occurred.
  DEP-001 still owns exact-SHA Railway deployment proof.
- Issue #42 is closed/released; implementation branches deleted. User-owned
  untracked skill directories, skills-lock.json and PROMPT-ORCHES.md remain
  preserved. High-risk delivery used GPT-6 root and Sol independent reviews;
  the renewed Standards cycle and merge verification took approximately ten
  minutes/9k context tokens. Earlier cycles remain in the task history.
- Next: ING-004, then OBS-001, ING-005, OPS-002, publication/deployment recovery,
  PIT integrity, analytics validation and gated provenance/promotion in roadmap
  order. Keep models SHADOW when evidence does not support promotion.
  Rollback is reviewed code revert/forward fix retaining evidence, never
  production down migrations.

The September 7 and August sections below are historical; this checkpoint
supersedes their present-tense implementation and next-task statements.

## Current checkpoint — 2026-09-07

- UX-003 merged via PR #38 as `01efe9e`, from base `26d4508` and reviewed
  head `5bb36345aa96c1ab2485dcc103af8fba26c84a34`. PastiCuan is Telegram-only:
  standalone Streamlit entry point, UI, configuration, dependency profile,
  and deployment instructions are removed. Telegram runtime and all research
  calculation paths are unchanged.
- All eight required checks passed in `34076961630`. Independent Sol/high
  Standards and Spec reviews each reported zero findings on that exact head.
  Main verification `34077063021` passed. The remote task branch was deleted;
  issue #37 is closed and its claim label released.
- Post-merge research run `34077063058` passed cache setup and dependency
  installation, then failed closed with exit 40, `INFRASTRUCTURE`,
  `REQUIRED_MIGRATION_MISSING`. No production recovery is claimed.
  Migration 007 remains without rollout authorization or production proof.
- No Supabase MCP query, schema application, secret operation, or manual
  production dispatch was performed. Exact-SHA Railway proof remains DEP-001.
  Backup, validation, and filing workflows were not manually dispatched;
  their changed cache inputs and policy were verified locally and in CI.
- User-owned untracked `.agents/skills/supabase/`,
  `.agents/skills/supabase-postgres-best-practices/`, `skills-lock.json`,
  and `PROMPT-ORCHES.md` are preserved. The shared checkout remains on main
  at `26d4508`; task worktrees do not depend on its untracked files.
- Next: ING-003 code/test work, with migration-007 preflight blocking production
  import. Then update this handoff before ING-004. Follow the dependency-ordered
  roadmap; statistical validation remains SHADOW and no promotion is authorized.

The sections below retain the August incident baseline and historical workspace
notes; the current checkpoint above supersedes their present-tense status.

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
- Scheduled `idx-filings` run `32685938136` failed closed on 2026-08-24 while merging the discovered draft into its review branch, before commit, push, or PR handling, because JPFA Q2 2026 provenance conflicted with the reviewed identity. Resolve that conflict through official evidence review; never overwrite the reviewed manifest identity or provenance to make discovery pass.
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
