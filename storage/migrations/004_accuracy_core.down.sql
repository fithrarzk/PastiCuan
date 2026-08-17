BEGIN;
DROP TABLE IF EXISTS market_research_snapshots;
DROP TABLE IF EXISTS disclosure_events;
DROP TABLE IF EXISTS signal_outcomes;
DROP TABLE IF EXISTS scan_signals;
DROP TABLE IF EXISTS research_job_runs;
DROP TABLE IF EXISTS provider_runs;
ALTER TABLE corporate_actions
  DROP COLUMN IF EXISTS quarantine_reason,
  DROP COLUMN IF EXISTS quarantined_at,
  DROP COLUMN IF EXISTS validation_status,
  DROP COLUMN IF EXISTS subscription_price,
  DROP COLUMN IF EXISTS source_class,
  DROP COLUMN IF EXISTS published_at;
ALTER TABLE statement_facts
  DROP COLUMN IF EXISTS fiscal_quarter,
  DROP COLUMN IF EXISTS fiscal_year,
  DROP COLUMN IF EXISTS duration_class,
  DROP COLUMN IF EXISTS period_type;
DELETE FROM schema_migrations WHERE version='004_accuracy_core';
COMMIT;
