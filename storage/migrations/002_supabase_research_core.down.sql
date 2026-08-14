BEGIN;
DROP TABLE IF EXISTS quant_research_snapshots;
DROP FUNCTION IF EXISTS enforce_quant_snapshot_validation();
DROP TABLE IF EXISTS validation_runs;
DROP TABLE IF EXISTS ingestion_issues;
DROP TABLE IF EXISTS source_artifacts;
DELETE FROM model_versions mv WHERE mv.id = '3.0.0-shadow'
  AND NOT EXISTS (SELECT 1 FROM analysis_snapshots a WHERE a.analysis_version = mv.id);
ALTER TABLE model_versions DROP CONSTRAINT IF EXISTS model_versions_status_check;
UPDATE model_versions SET status = 'VALIDATED' WHERE status = 'VALIDATED_RESEARCH';
ALTER TABLE model_versions ADD CONSTRAINT model_versions_status_check
  CHECK (status IN ('DRAFT','SHADOW','VALIDATED','RETIRED'));
DELETE FROM schema_migrations WHERE version = '002_supabase_research_core';
COMMIT;
