BEGIN;
DROP TABLE IF EXISTS alert_deliveries;
DROP TABLE IF EXISTS signals;
DROP TABLE IF EXISTS derived_metrics;
DROP TABLE IF EXISTS analysis_snapshots;
DROP TABLE IF EXISTS model_versions;
DROP TABLE IF EXISTS policy_rates;
DROP TABLE IF EXISTS fx_rates;
DROP TABLE IF EXISTS shares_history;
DROP TABLE IF EXISTS statement_facts;
DROP TABLE IF EXISTS filings;
DROP TABLE IF EXISTS corporate_actions;
DROP TABLE IF EXISTS market_bars;
DROP TABLE IF EXISTS market_sessions;
DROP TABLE IF EXISTS index_constituents;
DROP TABLE IF EXISTS issuers;
DROP TABLE IF EXISTS schema_migrations;
COMMIT;

