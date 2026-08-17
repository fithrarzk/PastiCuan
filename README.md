# PastiCuan

PastiCuan is an end-of-session IDX research system. Version 4 runs in **shadow
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

`/scan [ticker ...]` reads the latest immutable full-LQ45 end-of-day result.
Optional tickers filter that already-ranked snapshot; they never create a small
comparison universe or trigger live provider requests. `/quant <ticker>` remains
a separate exploratory comparison against the default watchlist and is not the
approved quant input used by `/scan`.

How to run
`streamlit run app.py`

## Reliability architecture

- Streamlit and Telegram share versioned analysis contracts. Their Scanner
  views both read the same immutable full-universe snapshot.
- Current Yahoo access is a flagged market-data fallback. It is not treated as
  authoritative fundamental data, so the action gate remains closed.
- Canonical structured research data uses Supabase PostgreSQL; original filing
  documents and logical backups use optional S3-compatible R2 storage. Apply
  migrations `001` through `004`, followed by `storage/supabase_roles.sql`.
- Railway runs only the Telegram webhook. GitHub Actions performs source
  acquisition, candidate snapshot construction and backups outside the request
  path. The bot caches approved, checksummed database snapshots; a transient
  database failure keeps the last in-process scan, while a cold start fails
  closed as UNAVAILABLE. The separate quant command can use a bundled fallback.
- `/scan` is quality-first: the long-horizon Business Score ranks point-in-time
  quality, valuation, durability, and resilience. Technical evidence, liquidity,
  executable IDX tick geometry, and 1.5R–5R planned risk/reward only decide entry
  readiness; they cannot raise the Business Score. Missing or incomplete official
  evidence produces a scoreless DEGRADED/LIMITED result instead of an estimate.
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
python -m operations.research_cli discover-idx-xbrl \
  --output idx-manifest-draft.json --as-of 2026-08-16T16:15:00+07:00 \
  --year 2026 --period tw2
python -m operations.research_cli ingest-idx-xbrl \
  --manifest data/idx_filing_manifest.json --report idx-xbrl-report.json --r2
python -m operations.research_cli build-snapshot-from-database \
  --output data/snapshots/candidate.json.gz \
  --effective-at 2026-08-31T16:15:00+07:00
python -m operations.research_cli validate-quant \
  --scores reviewed/monthly_scores.csv --bars reviewed/market_bars.csv \
  --output validation-report.json --persist --deterministic-rebuild
python -m operations.research_cli publish-reviewed-shadow \
  --candidate data/snapshots/candidate.json.gz \
  --output data/snapshots/latest.json.gz
python -m operations.research_cli build-daily-scan \
  --output scan-report.json --r2
python -m operations.research_cli evaluate-signal-outcomes
```

Candidate snapshots cannot be loaded by the bot. Approval changes the status
and checksum explicitly. `VALIDATED_RESEARCH` additionally requires a persisted
passing validation-run ID. Keep a model in `SHADOW` until those frozen gates
pass; neither status can make the bot emit an actionable recommendation.

`data/idx_filing_manifest.json` contains only metadata and official IDX
attachment URLs; do not commit filing binaries. The job downloads each XBRL
instance, archives the immutable original to R2 when configured, imports only
the reviewed factor concepts, and quarantines malformed or mismatched files.
The discovery command only creates a review draft; it never imports data.
Because IDX sometimes challenges automated clients, copying attachment URLs
from the official page into the checked manifest is the deterministic fallback.
No manual upload to R2 is required.

The daily scan command requires exactly 45 effective LQ45 constituents in
Supabase. GitHub Actions runs it after the weekday IDX close and publishes only
PRIMARY or DEGRADED SHADOW snapshots. An UNAVAILABLE build fails without
replacing the last good snapshot. Railway caches the latest database result for
5 minutes (bounded to 15) and performs no Yahoo, R2, backtest, or full-universe calculation in
the `/scan` request path.

## Narrative policy

Version 4 produces its report deterministically from the versioned evidence
bundle. Generative providers are outside the validated core: they cannot alter
facts, factor scores, gates, or verdicts. Keep `AI_PROVIDER=off` in production.
