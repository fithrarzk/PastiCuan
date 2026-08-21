# Model-card index

This index records identity and status, not a claim that a formula is validated or action-eligible.

| Model/card | Implementation | Evidence and status |
| --- | --- | --- |
| LQ45 cross-sectional v4 + business quality v2 | `analysis/quant.py`, `analysis/business.py`, `analysis/factor_dataset.py` | Current formula identity; `SHADOW` until persisted validation gates pass |
| Technical and price-range evidence | `analysis/technical.py`, `analysis/buy_range.py`, `analysis/valuation_bands.py` | Research range/timing evidence, never an order instruction; not a validated recommendation |
| Daily full-universe scan | `analysis/scan_v2.py`, `analysis/scan_snapshots.py` | Requires effective 45-member universe and evidence gates; may be `PRIMARY`, `DEGRADED`, or `UNAVAILABLE` |
| Signal outcomes v1 | `analysis/outcomes.py`, `operations/research_cli.py` | Observational forward outcomes at 5/20/60/252 sessions; not proof of predictive validity |

## Required card fields for future validation

Record universe and membership period, formula/release identity, point-in-time data sources, availability cutoff, exclusions and fallback policy, costs and delayed execution, deterministic rebuild, holdout period, drawdown/breadth/rank-IC/information-ratio gates, and persisted validation-run ID. Promotion to `VALIDATED_RESEARCH` requires the repository validation check; environment variables cannot promote a model.

Roadmap validation and release work must not be documented as complete until its task evidence exists.
