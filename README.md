# PastiCuan

PastiCuan is an end-of-session IDX research system. Version 2 runs in **shadow
mode**: it publishes reproducible evidence and paper alerts, but no Buy/Sell
label is eligible until the source, freshness, liquidity, broker-cost,
walk-forward validation, and 60-completed-session gates all pass. No model can
guarantee profit.

How to run
`streamlit run app.py`

## Reliability architecture

- Streamlit and Telegram call the same `run_analysis_bundle` orchestration path
  and consume the same versioned `AnalysisBundle` values.
- Current Yahoo access is a flagged market-data fallback. It is not treated as
  authoritative fundamental data, so the action gate remains closed.
- Production persistence is PostgreSQL; original filing documents are retained
  in S3-compatible object storage. Apply
  `storage/migrations/001_point_in_time_schema.up.sql`; its paired `.down.sql`
  migration is the explicit rollback.
- Financial facts carry their period, publication/availability timestamps,
  currency, scale, consolidation/audit status, source, checksum and restatement
  version. Point-in-time queries must filter `available_at <= as_of`.
- Prices and corporate actions remain separate. Signals are calculated after a
  completed close and can execute no earlier than the next tradable open.
- Without every `BROKER_*` field, backtests are gross research results and
  cannot influence an action.

Run the offline reliability suite with:

```bash
python -m unittest discover -s tests -v
```

## Local AI setup

PastiCuan can generate the AI Research Report with a local Ollama model, so the
core app does not depend on paid API calls.

1. Install Ollama from https://ollama.com/download
2. Pull the default model:

```bash
ollama pull qwen2.5:7b
```

3. Copy `.env.example` to `.env`, then keep:

```bash
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

4. Start the app:

```bash
streamlit run app.py
```

If Ollama is not running or the model is missing, the app will still generate a
deterministic local report from the technical/fundamental engine.
