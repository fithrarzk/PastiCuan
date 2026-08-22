BEGIN;

CREATE TABLE filing_work_items (
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    filing_type text NOT NULL CHECK (filing_type <> '' AND filing_type = btrim(filing_type) AND filing_type = upper(filing_type)),
    period_end date NOT NULL,
    restatement_version integer NOT NULL CHECK (restatement_version > 0),
    source_url text NOT NULL CHECK (source_url <> '' AND source_url = btrim(source_url)),
    published_at timestamptz NOT NULL,
    audit_status text NOT NULL CHECK (audit_status IN ('AUDITED','UNAUDITED','REVIEWED','UNKNOWN')),
    expected_checksum text,
    state text NOT NULL DEFAULT 'PENDING'
      CHECK (state IN ('PENDING','RUNNING','ACCEPTED','QUARANTINED','RETRYABLE')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    lease_token uuid,
    lease_owner text,
    lease_expires_at timestamptz,
    accepted_artifact_id uuid REFERENCES source_artifacts(id),
    accepted_checksum text,
    last_error_class text,
    last_error_summary text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (issuer_id, filing_type, period_end, restatement_version),
    CHECK (
      (state = 'RUNNING') =
      (lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_owner <> '' AND lease_expires_at IS NOT NULL)
    ),
    CHECK (state <> 'RUNNING' OR lease_expires_at > created_at),
    CHECK (state NOT IN ('ACCEPTED','QUARANTINED') OR accepted_artifact_id IS NOT NULL OR state = 'QUARANTINED'),
    CHECK (state <> 'ACCEPTED' OR accepted_checksum IS NOT NULL)
);

CREATE TABLE filing_work_attempts (
    id uuid PRIMARY KEY,
    issuer_id bigint NOT NULL,
    filing_type text NOT NULL,
    period_end date NOT NULL,
    restatement_version integer NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    lease_token uuid NOT NULL,
    worker_id text NOT NULL CHECK (worker_id <> ''),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    outcome_state text CHECK (outcome_state IS NULL OR outcome_state IN ('ACCEPTED','QUARANTINED','RETRYABLE')),
    error_class text,
    error_summary text,
    artifact_id uuid REFERENCES source_artifacts(id),
    source_url text,
    checksum text,
    FOREIGN KEY (issuer_id, filing_type, period_end, restatement_version)
      REFERENCES filing_work_items(issuer_id, filing_type, period_end, restatement_version),
    UNIQUE (issuer_id, filing_type, period_end, restatement_version, lease_token),
    UNIQUE (issuer_id, filing_type, period_end, restatement_version, attempt_number),
    CHECK ((finished_at IS NULL) = (outcome_state IS NULL)),
    CHECK (finished_at IS NULL OR error_summary IS NULL OR length(error_summary) <= 500),
    CHECK (error_class IS NULL OR error_class IN ('TRANSIENT','PROVIDER','DATABASE','VALIDATION','SCHEMA','PROVENANCE','CONFLICT','UNKNOWN'))
);

CREATE INDEX filing_work_items_state_idx
  ON filing_work_items(state, lease_expires_at, period_end, issuer_id, filing_type);
CREATE INDEX filing_work_attempts_identity_idx
  ON filing_work_attempts(issuer_id, filing_type, period_end, restatement_version, attempt_number);

CREATE FUNCTION enforce_filing_work_item_transition() RETURNS trigger AS $$
BEGIN
  IF NEW.issuer_id <> OLD.issuer_id
     OR NEW.filing_type <> OLD.filing_type
     OR NEW.period_end <> OLD.period_end
     OR NEW.restatement_version <> OLD.restatement_version
     OR NEW.source_url <> OLD.source_url
     OR NEW.published_at <> OLD.published_at
     OR NEW.audit_status <> OLD.audit_status
     OR NEW.expected_checksum IS DISTINCT FROM OLD.expected_checksum
     OR NEW.created_at <> OLD.created_at THEN
    RAISE EXCEPTION 'reviewed filing provenance is immutable';
  END IF;
  IF OLD.state IN ('ACCEPTED','QUARANTINED') AND NEW.state <> OLD.state THEN
    RAISE EXCEPTION 'terminal filing work cannot transition';
  END IF;
  IF OLD.state = 'PENDING' AND NEW.state NOT IN ('PENDING','RUNNING') THEN
    RAISE EXCEPTION 'illegal filing work transition';
  END IF;
  IF OLD.state = 'RETRYABLE' AND NEW.state NOT IN ('RETRYABLE','RUNNING') THEN
    RAISE EXCEPTION 'illegal filing work transition';
  END IF;
  IF OLD.state = 'RUNNING' AND NEW.state NOT IN ('RUNNING','ACCEPTED','QUARANTINED','RETRYABLE') THEN
    RAISE EXCEPTION 'illegal filing work transition';
  END IF;
  IF NEW.state = 'RUNNING' AND (NEW.lease_token IS NULL OR NEW.lease_owner IS NULL OR NEW.lease_expires_at IS NULL) THEN
    RAISE EXCEPTION 'running filing work requires a complete lease';
  END IF;
  IF NEW.state <> 'RUNNING' AND (NEW.lease_token IS NOT NULL OR NEW.lease_owner IS NOT NULL OR NEW.lease_expires_at IS NOT NULL) THEN
    RAISE EXCEPTION 'non-running filing work cannot retain a lease';
  END IF;
  IF NEW.state = 'ACCEPTED' AND (NEW.accepted_artifact_id IS NULL OR NEW.accepted_checksum IS NULL) THEN
    RAISE EXCEPTION 'accepted filing work requires an artifact and checksum';
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER filing_work_item_transition_guard
BEFORE UPDATE ON filing_work_items
FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_item_transition();

CREATE FUNCTION prevent_filing_work_attempt_mutation() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'filing work attempts are append-only';
  END IF;
  IF NEW.issuer_id <> OLD.issuer_id OR NEW.filing_type <> OLD.filing_type
     OR NEW.period_end <> OLD.period_end OR NEW.restatement_version <> OLD.restatement_version
     OR NEW.attempt_number <> OLD.attempt_number OR NEW.lease_token <> OLD.lease_token
     OR NEW.worker_id <> OLD.worker_id OR NEW.started_at <> OLD.started_at THEN
    RAISE EXCEPTION 'filing work attempt identity is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER filing_work_attempts_immutable_guard
BEFORE UPDATE OR DELETE ON filing_work_attempts
FOR EACH ROW EXECUTE FUNCTION prevent_filing_work_attempt_mutation();

CREATE FUNCTION enforce_filing_work_acceptance() RETURNS trigger AS $$
DECLARE artifact source_artifacts%ROWTYPE;
BEGIN
  IF NEW.state = 'ACCEPTED' THEN
    SELECT * INTO artifact FROM source_artifacts WHERE id = NEW.accepted_artifact_id;
    IF NOT FOUND OR artifact.parse_status <> 'ACCEPTED'
       OR artifact.source_url <> NEW.source_url
       OR (NEW.expected_checksum IS NOT NULL AND artifact.checksum <> NEW.expected_checksum) THEN
      RAISE EXCEPTION 'accepted filing work requires matching accepted artifact';
    END IF;
    NEW.accepted_checksum := artifact.checksum;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER filing_work_acceptance_guard
BEFORE INSERT OR UPDATE ON filing_work_items
FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_acceptance();

INSERT INTO schema_migrations(version) VALUES ('007_filing_work_ledger');
COMMIT;
