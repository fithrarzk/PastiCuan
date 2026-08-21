# Snapshot Lifecycle

## Atomic research release

A refresh builds quant and scan candidates without changing bot-visible state. It validates the pair, signs their immutable payloads, then appends one release activation that names the research release (formula identity), quant snapshot, scan snapshot, code SHA, calculation digest, evidence cutoff, actor, and timestamp.

Bot commands resolve all research evidence through that single active release. They must never independently choose the latest quant and latest scan rows.

## States

- Candidate: diagnostic and immutable, not active.
- Active: the one signed quant/scan pair selected by a release activation.
- Last good: the most recent active pair that passed publication and post-publication verification.
- Revoked: disallowed for current use but retained for audit.

## Failure behavior

- Failure before activation leaves every active ID unchanged.
- Stale evidence remains inspectable as historical evidence but cannot pass current action gates.
- Rollback appends a new release activation/revocation event pointing to a prior verified immutable pair.
- Schema rollback uses forward repair; it never deletes evidence or runs destructive down migrations automatically.

## Command contract

`/scan`, `/range`, `/decision`, `/quant`, `/status`, and evidence commands report the same release and snapshot identity. Unavailability is structured as stale, excluded, missing evidence, quarantine, provider failure, or no reliable setup; it is not collapsed into a generic empty result.

## Acceptance scenarios

1. Inject failure after quant candidate creation; active quant and scan IDs both remain unchanged.
2. Activate a valid pair; every command resolves the same release ID.
3. Revoke the newest pair; activation of last good preserves immutable payloads and audit history.
4. A stale pair exposes labeled historical detail while ranking and action gates remain closed.
