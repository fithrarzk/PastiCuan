BEGIN;

CREATE OR REPLACE FUNCTION enforce_filing_work_acceptance() RETURNS trigger AS $$
DECLARE artifact source_artifacts%ROWTYPE;
BEGIN
  IF NEW.state IN ('ACCEPTED','QUARANTINED') THEN
    SELECT * INTO artifact FROM source_artifacts WHERE id = NEW.artifact_id FOR SHARE;
    IF NOT FOUND OR artifact.parse_status <> NEW.artifact_status OR artifact.source_url <> NEW.source_url
       OR (NEW.expected_checksum IS NOT NULL AND artifact.checksum <> NEW.expected_checksum)
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

DELETE FROM schema_migrations WHERE version = '008_filing_artifact_mismatch';
COMMIT;
