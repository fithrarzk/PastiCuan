# Command and data dictionary

Commands are defined in [`operations/research_cli.py`](../../operations/research_cli.py). Inputs and outputs below describe current interfaces; accepted contracts are labelled explicitly.

| Interface | Owner | Inputs → output | Evidence identity / availability | Public test seam |
| --- | --- | --- | --- | --- |
| `ingest-manifest` | `data`, operations | reviewed source manifest → JSON report | source URL, checksum, published/retrieved times; parse failures quarantine | `tests/` ingestion and CLI tests |
| `discover-idx-xbrl` | `data` | `as-of`, year/period → draft manifest | official URL and filing identity; draft is not evidence | discovery tests |
| `ingest-idx-xbrl` | `data`/storage | reviewed IDX manifest → report and accepted artifacts | filing identity, checksum, `available_at` | XBRL/parser tests |
| `refresh-market-history` | operations/storage | source manifest and provider policy → market report | session date, provider and availability | market history tests |
| `run-daily-research` | operations/analysis | release, database, optional R2, final-attempt → run report and candidate/publication attempts | release ID, formula version, evidence cutoff, snapshot checksum | workflow/CLI tests |
| `build-daily-scan` | analysis/storage | accepted database evidence → scan report | session, mode, coverage, quant snapshot ID, checksum | scan snapshot tests |
| `validate-quant` | analysis | reviewed score/bar panels → validation report (optionally persisted) | model version, validation run ID and gates | validation tests |
| `publish-reviewed-shadow` | operations/storage | reviewed candidate → signed approved snapshot | status `SHADOW`, checksum, signature and release metadata | snapshot/signing tests |
| `backup` | operations/storage | database and encrypted output path → backup artifact | backup timestamp and checksum; R2 upload is strict | backup tests |
| `/`, `/ready` | delivery | webhook service/readiness request → health/release identity | approved snapshot and scan IDs; readiness is not exact-SHA proof | `bot_webhook` tests |
| `/scan`, `/range`, `/decision`, `/quant`, `/status` | delivery | optional ticker/filter → research response | same approved snapshot/release; stale or missing evidence is structured | bot command tests |

Primary stores are Supabase tables defined by [`storage/migrations/`](../../storage/migrations/) and optional R2 archives. `data/snapshots/candidate.json.gz` is a candidate artifact, never bot-readable evidence. Signed approved snapshots carry model status, effective time, formula/release identity, checksum, and signature.

The accepted contract names durable resumability and atomic release activation, but those are planned capabilities, not current dictionary guarantees.
