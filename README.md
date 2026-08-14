# PastiCuan

PastiCuan is an end-of-session IDX research system. Version 3 runs in **shadow
mode**: it publishes reproducible evidence and paper alerts, but no Buy/Sell
label is eligible until the source, freshness, liquidity, broker-cost,
walk-forward validation, and 60-completed-session gates all pass. No model can
guarantee profit.

## Free deployment

The deployment is optimized for a bot-first, scale-to-zero free-tier setup:

- Telegram bot: Railway Free webhook using `railway.json`, `Dockerfile`, and
  `requirements-bot.txt`. Cloud Run remains an optional metered alternative.
- App: Streamlit Community Cloud using `app.py` and `requirements.txt`.

Follow [DEPLOY_FREE.md](DEPLOY_FREE.md) from start to finish. The bot supports
`/range <ticker>` for a separately reported technical zone, historical
valuation reference, and preferred overlap; fallback fundamentals keep it
explicitly research-only.

`/scan [ticker ...]` ranks a bounded 5–10 name watchlist using the same shared
technical, fundamental, cross-sectional quant, range-alignment, liquidity, and
data-quality contract as Streamlit. `/quant <ticker>` reports the ticker's
relative percentile within the current default comparison universe.

How to run
`streamlit run app.py`

## Reliability architecture

- Streamlit and Telegram call the same `run_analysis_bundle` orchestration path
  and consume the same versioned `AnalysisBundle` values.
- Current Yahoo access is a flagged market-data fallback. It is not treated as
  authoritative fundamental data, so the action gate remains closed.
- Canonical structured research data uses Supabase PostgreSQL; original filing
  documents and logical backups use optional S3-compatible R2 storage. Apply
  migrations `001` then `002`, followed by `storage/supabase_roles.sql`.
- Railway runs only the Telegram webhook. GitHub Actions performs source
  acquisition, candidate snapshot construction and backups outside the request
  path. The bot caches an approved, checksummed snapshot and safely falls back
  to the bundled snapshot when Supabase is unavailable.
- Financial facts carry their period, publication/availability timestamps,
  currency, scale, consolidation/audit status, source, checksum and restatement
  version. Point-in-time queries must filter `available_at <= as_of`.
- Prices and corporate actions remain separate. Signals are calculated after a
  completed close and can execute no earlier than the next tradable open.
- Without every `BROKER_*` field, backtests are gross research results and
  cannot influence an action.
- `VALIDATED_RESEARCH` can only come from persisted validation evidence. No
  environment variable can promote a model, and action eligibility is not
  supported by the current policy.

Run the offline reliability suite with:

```bash
python -m unittest discover -s tests -v
```

## Research-core jobs

Install the job-only dependencies locally with
`pip install -r requirements-jobs.txt`. Core commands are:

```bash
python -m operations.research_cli ingest-manifest \
  --manifest data/source_manifest.json --report ingestion-report.json
python -m operations.research_cli build-snapshot-from-database \
  --output data/snapshots/candidate.json.gz \
  --effective-at 2026-08-31T16:15:00+07:00
python -m operations.research_cli validate-quant \
  --scores reviewed/monthly_scores.csv --bars reviewed/market_bars.csv \
  --output validation-report.json --persist
python -m operations.research_cli approve-snapshot \
  --candidate data/snapshots/candidate.json.gz \
  --output data/snapshots/latest.json.gz --status SHADOW
python -m operations.research_cli publish-snapshot \
  --snapshot data/snapshots/latest.json.gz
```

Candidate snapshots cannot be loaded by the bot. Approval changes the status
and checksum explicitly. `VALIDATED_RESEARCH` additionally requires a persisted
passing validation-run ID. Keep a model in `SHADOW` until those frozen gates
pass; neither status can make the bot emit an actionable recommendation.

## Narrative policy

Version 3 produces its report deterministically from the versioned evidence
bundle. Generative providers are outside the validated core: they cannot alter
facts, factor scores, gates, or verdicts. Keep `AI_PROVIDER=off` in production.
