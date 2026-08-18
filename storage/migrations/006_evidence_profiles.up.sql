BEGIN;
ALTER TABLE issuers
  ADD COLUMN IF NOT EXISTS profile_verified_at timestamptz,
  ADD COLUMN IF NOT EXISTS profile_source_url text,
  ADD COLUMN IF NOT EXISTS profile_checksum text;
ALTER TABLE issuers DROP CONSTRAINT IF EXISTS issuers_issuer_type_check;
ALTER TABLE issuers ADD CONSTRAINT issuers_issuer_type_check
  CHECK (issuer_type IN ('general','bank'));
INSERT INTO schema_migrations(version) VALUES ('006_evidence_profiles')
ON CONFLICT (version) DO NOTHING;
COMMIT;
