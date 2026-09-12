# Command and data dictionary

Commands are defined in [`operations/research_cli.py`](../../operations/research_cli.py). Inputs and outputs below describe current interfaces; accepted contracts are labelled explicitly.

| Interface | Owner | Inputs → output | Evidence identity / availability | Public test seam |
| --- | --- | --- | --- | --- |
| `ingest-manifest` | `data`, operations | reviewed source manifest → JSON report | source URL, checksum, published/retrieved times; parse failures quarantine; report metadata alone does not establish `available_at` eligibility | no direct CLI seam |
| `discover-idx-xbrl` | `data` | `as-of`, year/period → draft manifest | official URL and filing identity; draft is not evidence | [`tests/test_idx_xbrl.py`](../../tests/test_idx_xbrl.py) (`IdxDiscoveryTests`) |
| `data.filing_manifest` | `data`/CI | reviewed baseline + discovery draft → atomically merged review manifest | exact identity `(ticker, filing_type, period_end, restatement_version)`; URL, publication timestamp, audit status, and checksum are provenance; no `available_at` is synthesized | [`tests/test_filing_manifest.py`](../../tests/test_filing_manifest.py) |
| `ingest-idx-xbrl` | `data`/storage | reviewed IDX manifest, shard/batch/retry/budget policy or aggregation-only mode → redacted shard/durable-progress report and accepted artifacts | filing identity, checksum, `available_at`; deterministic issuer/reporting-year shard; durable attempt/run identity; aggregation distinguishes batch acceptance from prior accepted skips | [`tests/test_idx_filing_importer.py`](../../tests/test_idx_filing_importer.py), [`tests/test_idx_filing_shards.py`](../../tests/test_idx_filing_shards.py), and disposable PostgreSQL cases in [`tests/test_filing_work_ledger.py`](../../tests/test_filing_work_ledger.py) |
| `refresh-market-history` | operations/storage | `--output`; effective LQ45 membership from Supabase plus configured market loader/provider policy → market report | completed session, provider, and availability; failure returns non-ready report | no direct CLI seam |
| `run-daily-research` | operations/analysis | release, database, optional R2, final-attempt → run report and publication attempts | release ID, formula version, evidence cutoff, snapshot checksum; quant may publish before a later scan failure | [`tests/test_research_automation.py`](../../tests/test_research_automation.py); no direct CLI seam |
| `build-daily-scan` | analysis/storage | accepted database evidence → scan report | session, mode, coverage, quant snapshot ID, checksum; non-published result exits non-zero | [`tests/test_scan_v2.py`](../../tests/test_scan_v2.py) |
| `validate-quant` | analysis | reviewed score/bar panels → validation report (optionally persisted) | model version, validation run ID and gates; only persisted passing evidence can validate | [`tests/test_core_v3.py`](../../tests/test_core_v3.py) (`QuantValidationTests`) |
| `publish-reviewed-shadow` | operations/storage | reviewed candidate → signed published `SHADOW` snapshot | status, checksum, signature and release metadata; candidate remains non-loadable | [`tests/test_core_v3.py`](../../tests/test_core_v3.py) (`SnapshotContractTests`); no direct CLI seam |
| `backup` | operations/storage | database and encrypted output path → pg_dump artifact | current command emits dump and optional encrypted upload; timestamp/checksum metadata is planned under `BAK-001` | no dedicated backup test seam |
| `/`, `/ready` | delivery | webhook service/readiness request → health/release identity | published snapshot and scan IDs; readiness is not exact-SHA proof | no dedicated `bot_webhook` test seam |
| `/scan`, `/range`, `/decision`, `/quant`, `/status` | delivery | optional ticker/filter → research response | same published snapshot/release where available; stale or missing evidence is structured | [`tests/test_scan_v2.py`](../../tests/test_scan_v2.py), [`tests/test_reliability.py`](../../tests/test_reliability.py); no route-level seam |

Primary stores are Supabase tables defined by [`storage/migrations/`](../../storage/migrations/) and optional R2 archives. `data/snapshots/candidate.json.gz` is a candidate artifact, never bot-readable evidence. Signed published snapshots carry model status, effective time, formula/release identity, checksum, and signature.

The accepted ingestion contract's skip-before-download, deterministic sharding,
bounded retry, and durable cross-shard progress behavior is implemented in code;
production use remains unavailable until migrations 007/008 satisfy the protected
rollout gates. Atomic release activation remains planned under REL-001.
