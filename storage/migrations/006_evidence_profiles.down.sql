BEGIN;
ALTER TABLE issuers DROP CONSTRAINT IF EXISTS issuers_issuer_type_check;
ALTER TABLE issuers
  DROP COLUMN IF EXISTS profile_verified_at,
  DROP COLUMN IF EXISTS profile_source_url,
  DROP COLUMN IF EXISTS profile_checksum;
DELETE FROM schema_migrations WHERE version='006_evidence_profiles';
COMMIT;
