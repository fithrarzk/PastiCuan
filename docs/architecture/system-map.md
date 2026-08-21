# System map

PastiCuan is a `RESEARCH_ONLY`, point-in-time IDX system. Production code is the merged `origin/main`; production research is accepted Supabase evidence plus signed published snapshots. A branch, candidate artifact, or local cache is not production truth.

## Boundaries and ownership

| Boundary | Owner and real entry points | Source of truth | Output |
| --- | --- | --- | --- |
| Acquisition and validation | `data/ingestion.py`, `data/idx_xbrl.py`, `data/validation.py` and `operations/research_cli.py` | Reviewed `data/source_manifest.json` and `data/idx_filing_manifest.json`; accepted/quarantined artifacts in storage | Evidence rows and ingestion reports |
| Persistence | `storage/repository.py`, `storage/database.py`, `storage/migrations/` | Supabase PostgreSQL; optional original archives in R2 | Point-in-time evidence, signals, snapshots |
| Analysis | `analysis/` (factor, business, technical, quant, scan modules) | Evidence selected with `available_at <= as_of` | Candidate quant and scan snapshots |
| Orchestration | `.github/workflows/`, `operations/research_cli.py` | Workflow run artifacts and signed release metadata | Reviewed publication attempt and reports |
| Delivery | `bot.py`, `bot_webhook.py`, `analysis/snapshots.py`, `analysis/scan_snapshots.py` | Approved signed snapshots; read-only database access | Telegram commands and `/ready` health |

Railway hosts only the Telegram webhook; GitHub Actions runs acquisition, refresh, publication and backup work outside the request path. Streamlit is a separate presentation service. The bot must not calculate a full-universe scan or call Yahoo/R2 in `/scan`.

## Status vocabulary

- **Implemented:** snapshot-only delivery, checksum/signature validation, point-in-time repository queries, CLI jobs, and fail-closed stale/unavailable states.
- **Accepted contract:** cumulative discovery, durable resumable import, one atomic quant/scan release activation, exact main-SHA deployment verification, and verified restore capability are specified in [the CI/CD contract](../specs/ci-cd-contract.md) and related contracts.
- **Planned/not yet proven:** do not describe those accepted contracts as production behavior until their roadmap tasks and evidence are complete. Analytics remain `SHADOW` until validation gates pass.
