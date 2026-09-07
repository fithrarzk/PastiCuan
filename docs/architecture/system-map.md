# System map

PastiCuan is a `RESEARCH_ONLY`, point-in-time IDX system. Production code is the merged `origin/main`; production research is accepted Supabase evidence plus signed published snapshots. A branch, candidate artifact, or local cache is not production truth.

## Boundaries and ownership

| Boundary | Owner and real entry points | Source of truth | Output |
| --- | --- | --- | --- |
| Acquisition and validation | [`data/ingestion.py`](../../data/ingestion.py), [`data/idx_xbrl.py`](../../data/idx_xbrl.py), [`data/validation.py`](../../data/validation.py), [`operations/research_cli.py`](../../operations/research_cli.py) | Reviewed [`data/source_manifest.json`](../../data/source_manifest.json) and [`data/idx_filing_manifest.json`](../../data/idx_filing_manifest.json); accepted/quarantined artifacts in storage | Evidence rows and ingestion reports |
| Persistence | [`storage/repository.py`](../../storage/repository.py), [`storage/database.py`](../../storage/database.py), [`storage/migrations/`](../../storage/migrations/) | Supabase PostgreSQL; optional original archives in R2 | Point-in-time evidence, signals, snapshots |
| Analysis | [`analysis/`](../../analysis/) (factor, business, technical, quant, scan modules) | Evidence selected with `available_at <= as_of` | Candidate quant and scan snapshots |
| Orchestration | [`.github/workflows/`](../../.github/workflows/), [`operations/research_cli.py`](../../operations/research_cli.py) | Workflow run artifacts and signed release metadata | Reviewed publication attempt and reports |
| Delivery | [`bot.py`](../../bot.py), [`bot_webhook.py`](../../bot_webhook.py), [`analysis/snapshots.py`](../../analysis/snapshots.py), [`analysis/scan_snapshots.py`](../../analysis/scan_snapshots.py) | Published signed snapshots; read-only database access | Telegram commands and `/ready` health |

Railway hosts only the Telegram webhook; GitHub Actions runs acquisition, refresh, publication and backup work outside the request path. The bot must not calculate a full-universe scan or call Yahoo/R2 in `/scan`.

## Status vocabulary

- **Implemented:** snapshot-only delivery, checksum/signature validation, point-in-time repository queries, CLI jobs, and fail-closed stale/unavailable states.
- **Accepted contract:** cumulative discovery and durable resumable import ([ingestion contract](../specs/ingestion-contract.md)), one atomic quant/scan release activation ([snapshot lifecycle](../specs/snapshot-lifecycle.md)), exact main-SHA deployment verification, and verified restore capability ([CI/CD contract](../specs/ci-cd-contract.md)) are planned contracts, not current guarantees.
- **Planned/not yet proven:** do not describe those accepted contracts as production behavior until their roadmap tasks and evidence are complete. Analytics remain `SHADOW` until validation gates pass.
