BEGIN;
DROP TABLE IF EXISTS scan_research_snapshots;
DROP FUNCTION IF EXISTS prevent_scan_snapshot_mutation();
DELETE FROM schema_migrations WHERE version = '003_scan_research_snapshots';
COMMIT;
