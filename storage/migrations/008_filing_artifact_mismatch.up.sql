BEGIN;

CREATE OR REPLACE FUNCTION enforce_filing_work_acceptance() RETURNS trigger AS $$
DECLARE artifact source_artifacts%ROWTYPE;
DECLARE allowed_mismatch boolean;
BEGIN
  IF NEW.state IN ('ACCEPTED','QUARANTINED') THEN
    SELECT * INTO artifact FROM source_artifacts WHERE id = NEW.artifact_id FOR SHARE;
    allowed_mismatch := NEW.state = 'QUARANTINED'
      AND NEW.last_error_class = 'PROVENANCE'
      AND NEW.last_error_summary = 'ARTIFACT_MISMATCH';
    IF allowed_mismatch AND (NEW.expected_checksum IS NULL OR artifact.checksum = NEW.expected_checksum) THEN
      RAISE EXCEPTION 'artifact mismatch quarantine requires a mismatch';
    END IF;
    IF NOT FOUND OR artifact.parse_status <> NEW.artifact_status OR artifact.source_url <> NEW.source_url
       OR (NEW.expected_checksum IS NOT NULL AND artifact.checksum <> NEW.expected_checksum AND NOT allowed_mismatch)
       OR NEW.artifact_checksum IS DISTINCT FROM artifact.checksum OR NEW.artifact_source_url IS DISTINCT FROM artifact.source_url THEN
      RAISE EXCEPTION 'filing work artifact provenance mismatch';
    END IF;
    IF NEW.state = 'ACCEPTED' AND artifact.parse_status <> 'ACCEPTED' THEN
      RAISE EXCEPTION 'accepted filing work requires accepted artifact';
    END IF;
    IF NEW.state = 'QUARANTINED' AND artifact.parse_status <> 'QUARANTINED' THEN
      RAISE EXCEPTION 'quarantined filing work requires quarantined artifact';
    END IF;
    NEW.accepted_artifact_id := CASE WHEN NEW.state = 'ACCEPTED' THEN NEW.artifact_id ELSE NULL END;
    NEW.accepted_checksum := CASE WHEN NEW.state = 'ACCEPTED' THEN NEW.artifact_checksum ELSE NULL END;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

INSERT INTO schema_migrations(version) VALUES ('008_filing_artifact_mismatch');
COMMIT;
