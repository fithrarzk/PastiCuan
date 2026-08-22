BEGIN;
DROP TABLE IF EXISTS filing_work_attempts;
DROP TABLE IF EXISTS filing_work_items;
DROP FUNCTION IF EXISTS enforce_filing_work_acceptance();
DROP FUNCTION IF EXISTS prevent_filing_work_attempt_mutation();
DROP FUNCTION IF EXISTS enforce_filing_work_item_transition();
DELETE FROM schema_migrations WHERE version = '007_filing_work_ledger';
COMMIT;
