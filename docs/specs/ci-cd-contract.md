# CI/CD Contract

## Delivery graph

```text
task worktree -> local tests -> task branch -> pull request
  -> classify change -> required parallel checks -> independent review
  -> squash auto-merge -> main orchestrator
  -> optional backup/migration -> resumable import -> atomic research build
  -> Railway deploy -> production smoke/freshness checks -> last-good marker
```

Routine code changes do not rerun official filing import unless their declared paths or contracts require it. Manifest changes do not start research concurrently with import.

## Pull-request checks

Stable required check names:

- `test`: lightweight compatibility context that fails unless `unit` succeeds;
- `unit`: compile, unit tests, deterministic release check, diff whitespace;
- `quality`: formatting, lint, and type checks with pinned tool versions;
- `workflow-policy`: YAML syntax, least privilege, pinned actions, concurrency, timeout, and recursion policy;
- `migration`: clean PostgreSQL apply, checksum ledger, repository integration, and compatibility tests;
- `container-smoke`: reproducible image build and webhook startup/health;
- `manifest-validate`: conditional official-host, identity, duplicate, regression, and removal checks;
- `security`: secret and dependency scanning.

Feature branches run the full suite once through `unit`; `test` preserves the
existing required context without repeating it. Avoid duplicate push suites.
Bot-generated PRs must receive the same checks. Use a GitHub App token or
explicit validation dispatch because pushes made by `GITHUB_TOKEN` do not
recursively trigger ordinary workflow runs.

## Merge policy

- Strict current-head required checks and resolved review threads.
- Independent spec/standards review.
- Squash merge only; delete head branches.
- Changes to workflows, migrations, signing/publication policy, or research formulas receive their additional class-specific checks.
- Missing, cancelled, neutralized, or stale checks are not green.

## Main orchestration

- Main pushes limited to documentation, tests, agent metadata, or CI-only files
  do not dispatch production research. Runtime paths, schedules, and manual
  dispatch retain the research workflow.
- Serialize production database writers with a PostgreSQL advisory lock.
- Apply only reviewed additive migrations after a verified backup.
- For manifest/data changes, complete resumable import before research refresh.
- Build and activate quant and scan as one atomic release.
- Deploy the exact main SHA to Railway and report deployment status against that SHA.
- Verify `/`, `/ready`, snapshot signature/readability, release IDs, and freshness.
- Record code SHA, deployment ID, active research release, and last-good state.

## Failure and recovery

- Keep prior active research and prior healthy deployment.
- Retry only classified transient stages with bounded attempts.
- Open or update one incident issue; do not create issue spam.
- Code recovery redeploys last-good SHA/image.
- Research recovery appends activation of a prior signed pair.
- Database recovery is forward-fix plus verified restore capability, never automatic destructive down migration.

## Credentials

Production secrets belong to protected GitHub environments and are referenced only by name. Separate ingest, publication, migration, Railway read, filing-archive, and backup roles where the providers allow it. Railway must not hold database writer, migrator, or signing-private-key credentials.
