# CI-002A: Supported yfinance dependency chain

- Status: review
- Priority: P0 prerequisite
- Owner/model: Luna implementation, Sol review
- Reasoning effort: medium implementation, high review
- Context budget: `AGENTS.md`, `CONTEXT.md`, this card, the two runtime requirement files, and only the named provider call sites/tests; maximum 18k tokens
- Retry ceiling: two bounded implementation cycles
- Escalation condition: the supported dependency chain requires provider API rewrites, changes research semantics, or cannot resolve on Python 3.12 without a security waiver
- Parallelism: one writer; independent review starts after implementation
- Base SHA: `693af474baa11d73ad41d116b626a1bb44e5ed3d`
- Branch: `fix/CI-002A-yfinance-compatibility`
- Worktree: `../PastiCuan-wt/ci-002a-yfinance-compatibility`
- Depends on: CI-001
- Blocks: CI-002
- File ownership: `requirements.txt`, `requirements-bot.txt`, `requirements-jobs.txt`, `tests/test_yfinance_compat.py` (new), this task card, `docs/tasks/ROADMAP.md`, and `docs/tasks/CLAIMS.md` (root orchestrator only). The implementation may change `data/stock.py`, `data/extended.py`, `analysis/portfolio.py`, or `ui/tabs/comparison.py` only when an offline characterization test proves a compatibility regression first.
- Merge policy: autonomous

## Outcome

Replace the unsupported `yfinance==1.2.0` / `curl-cffi==0.13.0` chain with a mutually supported, audited chain while preserving the repository's current public-provider call seams and fail-closed research behavior.

## Non-goals

- Rewrite provider acquisition or parsing.
- Add network-dependent tests or use Yahoo fundamental data as official evidence.
- Change source classes, formulas, freshness, publication, coverage, or risk gates.
- Waive or ignore a vulnerability to make CI-002 pass.

## Implementation contract

- Pin `yfinance==1.5.2`, `curl-cffi==0.16.1`, and `cryptography==50.0.0` consistently in both runtime requirement sets.
- In `requirements-bot.txt`, pin `fastapi==0.141.1` and its compatible transitive boundary `starlette==1.3.1` so the audit result is reproducible.
- Keep the redundant `cryptography` constraint in `requirements-jobs.txt` aligned with its included bot requirement so that job installs remain resolvable.
- Add offline characterization for the yfinance public interfaces used here: `Ticker` construction and `history`/`info`/quarterly attributes, plus `download`. Tests must not call the network or assert private provider internals.
- Preserve existing seams proving price-only paths do not request `.info` and injected portfolio history does not call the provider.
- Change a provider call site only if the new characterization first fails against the supported pins.

## Acceptance tests

- Fresh Python 3.12 environments install `requirements.txt` and `requirements-bot.txt`, and `pip check` passes in each.
- The installed yfinance metadata accepts `curl-cffi==0.16.1`.
- `pip-audit` reports zero known vulnerabilities for all three requirement files present at this base SHA; no advisory is ignored. After synchronization, CI-002 must also audit its new `requirements-ci.txt`.
- Focused compatibility tests and the full repository verification commands pass without network or production credentials.

## Rollout and rollback

Merge before CI-002, then synchronize the CI-002 branch and let its security gate prove the pins again. Roll back the pins and compatibility test together if deployment import/startup fails; keep CI-002 blocked rather than weakening its audit.

## Handoff

Implementation commits `9f74832`, `4f5d485`, and `6d2e25d` pin the supported chain and add seven offline compatibility tests; no provider call site changed. Fresh Python 3.12 installs and `pip check` passed for both runtime profiles. Strict audits reported no known vulnerabilities for `requirements.txt`, `requirements-bot.txt`, and `requirements-jobs.txt`; `requirements-ci.txt` does not exist at this base and remains a CI-002 verification obligation. Record final review, PR/check, merge SHA, and post-merge evidence before marking verified.
