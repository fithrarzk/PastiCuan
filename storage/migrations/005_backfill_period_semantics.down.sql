BEGIN;
-- Period classification is deterministic source metadata and remains valid on
-- rollback; only unregister the migration rather than erasing useful evidence.
DELETE FROM schema_migrations WHERE version='005_backfill_period_semantics';
COMMIT;
