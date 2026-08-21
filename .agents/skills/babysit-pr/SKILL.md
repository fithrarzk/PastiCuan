---
name: babysit-pr
description: Monitor a pull request through review and CI. Use when the user asks to watch, monitor, or babysit a PR.
metadata:
  harness: [claude, codex, opencode]
  platform: [darwin, linux]
  scope: ganesa-space
---

# Babysit PR

All the repos we work in have various AI review bots. They're helpful, even if they are not always right.

If your harness offers tools to monitor a PR, use them so you can respond when comments arrive. Otherwise, poll the PR for new comments and checks.

Only act on checks and comments newer than the latest push. Verify every bot finding against the source before changing code. Fix real findings and CI failures, distinguish repository failures from infrastructure flakes, and reply with a written reason when dismissing false positives.

Keep an eye on changes to `development`/`main` and rebase when needed. If an overlapping PR makes this one obsolete, stop monitoring, report it to the user, and ask before closing the PR unless closure was explicitly authorized.

If a review bot leaves feedback you believe is not worth addressing, reply and resolve the comment. Format comments left on the founder's behalf as:

```md
[MODEL-SLUG] RESPONDING ON BEHALF OF FOUNDER
-----

[actual reply]
```

Screenshots and videos help as well. Use the `file-upload` skill when needed.

Do not let review feedback expand the PR beyond the user's original goal. Address real shortcomings, but avoid scope creep.

If nothing has changed, stay quiet rather than posting filler comments. Stop when the review bots and required checks are green on the latest commit. Merge only when the user explicitly requested it; otherwise report that the PR is ready.

## LiveLaku ready gate (this repo)

A PR is ready only when:

- **CI green** on the current head (`backend` - pytest + contract, `docker` - compose build + healthcheck + smoke POST, `lint` - no em dash all pass) or local green when CI is limited by billing or runner (see How to babysit step 3)
- **A missing or unconfigured required gate is not green** — never invent a pass without local proof
- **Contract drift guard** passes (`pytest backend/tests/test_contract.py -v`)
- **Docker smoke** passes (`curl POST /analyze` returns `suggested_reply`)

## How to babysit here

1. **Poll:** `gh pr checks <number>` and `gh pr view <number> --comments` — compare timestamps against `git log --oneline -1` for the latest push.
2. **Verify:** open the flagged file/line, confirm the finding is real (not a stale review on an old commit).
3. **Fix:** smallest code or docs change that addresses the finding; push, then re-poll. If CI fails due to billing or runner limit, run the same checks **locally** and treat local green as the gate:
   ```bash
   pytest backend/tests/test_contract.py -v
   docker compose build
   docker compose up -d && curl -sf http://localhost:8000/api/health && curl -sf -X POST http://localhost:8000/analyze -H "Content-Type: application/json" -d '{"source":"mock","window_seconds":10,"comments":[{"text":"kak harga berapa?"}]}' | grep -q suggested_reply; docker compose down -v
   grep -R "—" --exclude-dir=.git --exclude-dir=.agents --exclude-dir=.claude --include="*.md" --include="*.yaml" --include="*.py" --include="*.js" --include="*.html" .
   ```
   Do not invent a pass when a required check is not green and no local proof exists.
4. **Waive:** if false positive, reply in thread with evidence and resolve: `[OPencode] RESPONDING ON BEHALF OF FOUNDER ...` + `gh api repos/.../pulls/.../comments/...` resolution if needed.
5. **Rebase:** if `development` moved, `git fetch origin && git rebase origin/development` or `git merge` as appropriate; push.
6. **Merge:** only with explicit user request and gate green — then `gh pr merge --squash --delete-branch`.

## Where to look

- CI: `.github/workflows/ci.yml`, `.github/workflows/docs.yml`
- Docs checks: `scripts/check-docs.mjs`
- Greptile thresholds: `AGENTS.md:Git, review, and documentation` and `docs/internals/pull-requests.md`
- Glossary for any term: `docs/reference/glossary.md`
