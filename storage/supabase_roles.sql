-- Run once as the Supabase database owner after applying migrations.
DO $$ BEGIN CREATE ROLE pasticuan_ingest NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE pasticuan_validator NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE ROLE pasticuan_bot NOLOGIN; EXCEPTION WHEN duplicate_object THEN NULL; END $$;

GRANT USAGE ON SCHEMA public TO pasticuan_ingest, pasticuan_validator, pasticuan_bot;
GRANT SELECT ON schema_migrations TO pasticuan_ingest, pasticuan_validator, pasticuan_bot;
GRANT SELECT, INSERT, UPDATE ON source_artifacts, ingestion_issues, issuers, index_constituents,
  market_sessions, market_bars, corporate_actions, filings, statement_facts, shares_history,
  fx_rates, policy_rates, provider_runs, research_job_runs, disclosure_events,
  filing_work_items, filing_work_attempts TO pasticuan_ingest;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pasticuan_ingest;
GRANT SELECT ON issuers, index_constituents, market_sessions, market_bars, corporate_actions,
  filings, statement_facts, shares_history, fx_rates, policy_rates, source_artifacts,
  filing_work_items, filing_work_attempts TO pasticuan_validator;
GRANT SELECT, INSERT, UPDATE ON model_versions, validation_runs, quant_research_snapshots,
  provider_runs, research_job_runs, signal_outcomes TO pasticuan_validator;
GRANT SELECT, INSERT ON scan_research_snapshots, scan_signals,
  market_research_snapshots TO pasticuan_validator;
GRANT SELECT ON model_versions, validation_runs, quant_research_snapshots,
  scan_research_snapshots, market_research_snapshots, provider_runs, research_job_runs,
  scan_signals, signal_outcomes, disclosure_events TO pasticuan_bot;

-- Create LOGIN users separately in the Supabase SQL editor and grant each one
-- exactly one group role. Never give the Railway user ingest/validator rights.
