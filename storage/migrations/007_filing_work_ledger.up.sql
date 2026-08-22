BEGIN;

CREATE TABLE filing_work_items (
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    filing_type text NOT NULL CONSTRAINT filing_work_filing_type_check CHECK (filing_type <> '' AND filing_type = btrim(filing_type) AND filing_type = upper(filing_type)),
    period_end date NOT NULL,
    restatement_version integer NOT NULL CONSTRAINT filing_work_restatement_check CHECK (restatement_version > 0),
    source_url text NOT NULL CONSTRAINT filing_work_source_url_check CHECK (source_url <> '' AND source_url = btrim(source_url)),
    published_at timestamptz NOT NULL,
    audit_status text NOT NULL CONSTRAINT filing_work_audit_status_check CHECK (audit_status IN ('AUDITED','UNAUDITED','REVIEWED','UNKNOWN')),
    expected_checksum text,
    state text NOT NULL DEFAULT 'PENDING' CONSTRAINT filing_work_state_check CHECK (state IN ('PENDING','RUNNING','ACCEPTED','QUARANTINED','RETRYABLE')),
    attempt_count integer NOT NULL DEFAULT 0 CONSTRAINT filing_work_attempt_count_check CHECK (attempt_count >= 0),
    lease_token uuid,
    lease_owner text,
    lease_expires_at timestamptz,
    artifact_id uuid REFERENCES source_artifacts(id),
    artifact_checksum text,
    artifact_source_url text,
    artifact_status text CHECK (artifact_status IS NULL OR artifact_status IN ('ACCEPTED','QUARANTINED')),
    accepted_artifact_id uuid REFERENCES source_artifacts(id),
    accepted_checksum text,
    last_error_class text,
    last_error_summary text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    state_changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT filing_work_identity_pkey PRIMARY KEY (issuer_id, filing_type, period_end, restatement_version),
    CONSTRAINT filing_work_lease_fields_check CHECK ((state = 'RUNNING') = (lease_token IS NOT NULL AND lease_owner IS NOT NULL AND lease_owner <> '' AND lease_expires_at IS NOT NULL)),
    CONSTRAINT filing_work_running_expiry_check CHECK (state <> 'RUNNING' OR lease_expires_at > created_at),
    CONSTRAINT filing_work_terminal_artifact_check CHECK (state IN ('PENDING','RUNNING','RETRYABLE') OR artifact_id IS NOT NULL),
    CONSTRAINT filing_work_accepted_status_check CHECK (state <> 'ACCEPTED' OR artifact_status = 'ACCEPTED'),
    CONSTRAINT filing_work_quarantine_reason_check CHECK (state <> 'QUARANTINED' OR (artifact_status = 'QUARANTINED' AND last_error_summary IS NOT NULL AND btrim(last_error_summary) <> '')),
    CONSTRAINT filing_work_accepted_artifact_check CHECK (state <> 'ACCEPTED' OR accepted_artifact_id = artifact_id),
    CONSTRAINT filing_work_accepted_checksum_check CHECK (state <> 'ACCEPTED' OR accepted_checksum = artifact_checksum),
    CONSTRAINT filing_work_error_class_check CHECK (last_error_class IS NULL OR last_error_class IN ('TRANSIENT','PROVIDER','DATABASE','VALIDATION','SCHEMA','PROVENANCE','CONFLICT','UNKNOWN')),
    CONSTRAINT filing_work_error_summary_check CHECK (last_error_summary IS NULL OR last_error_summary IN ('LEASE_EXPIRED','PROVIDER_UNAVAILABLE','DATABASE_UNAVAILABLE','VALIDATION_FAILED','SCHEMA_INVALID','PROVENANCE_CONFLICT','ARTIFACT_MISMATCH','UNKNOWN_FAILURE')),
    CONSTRAINT filing_work_error_class_length_check CHECK (last_error_class IS NULL OR length(last_error_class) <= 32),
    CONSTRAINT filing_work_error_summary_length_check CHECK (last_error_summary IS NULL OR length(last_error_summary) <= 64)
);

CREATE TABLE filing_work_attempts (
    id uuid PRIMARY KEY,
    issuer_id bigint NOT NULL,
    filing_type text NOT NULL,
    period_end date NOT NULL,
    restatement_version integer NOT NULL,
    attempt_number integer NOT NULL CONSTRAINT filing_work_attempt_number_check CHECK (attempt_number > 0),
    lease_token uuid NOT NULL,
    worker_id text NOT NULL CONSTRAINT filing_work_attempt_worker_check CHECK (worker_id <> ''),
    run_id text NOT NULL CONSTRAINT filing_work_attempt_run_check CHECK (run_id <> ''),
    lease_expires_at timestamptz NOT NULL,
    source_url text NOT NULL,
    expected_checksum text,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    outcome_state text CHECK (outcome_state IS NULL OR outcome_state IN ('ACCEPTED','QUARANTINED','RETRYABLE')),
    error_class text,
    error_summary text,
    artifact_id uuid REFERENCES source_artifacts(id),
    artifact_checksum text,
    artifact_source_url text,
    artifact_status text CHECK (artifact_status IS NULL OR artifact_status IN ('ACCEPTED','QUARANTINED')),
    CONSTRAINT filing_work_attempt_lease_unique UNIQUE (issuer_id, filing_type, period_end, restatement_version, lease_token),
    CONSTRAINT filing_work_attempt_number_unique UNIQUE (issuer_id, filing_type, period_end, restatement_version, attempt_number),
    CONSTRAINT filing_work_attempt_identity_fkey FOREIGN KEY (issuer_id, filing_type, period_end, restatement_version)
      REFERENCES filing_work_items(issuer_id, filing_type, period_end, restatement_version),
    CONSTRAINT filing_work_attempt_completion_check CHECK ((finished_at IS NULL) = (outcome_state IS NULL)),
    CONSTRAINT filing_work_attempt_error_class_check CHECK (error_class IS NULL OR error_class IN ('TRANSIENT','PROVIDER','DATABASE','VALIDATION','SCHEMA','PROVENANCE','CONFLICT','UNKNOWN')),
    CONSTRAINT filing_work_attempt_error_summary_check CHECK (error_summary IS NULL OR error_summary IN ('LEASE_EXPIRED','PROVIDER_UNAVAILABLE','DATABASE_UNAVAILABLE','VALIDATION_FAILED','SCHEMA_INVALID','PROVENANCE_CONFLICT','ARTIFACT_MISMATCH','UNKNOWN_FAILURE')),
    CONSTRAINT filing_work_attempt_error_class_length_check CHECK (error_class IS NULL OR length(error_class) <= 32),
    CONSTRAINT filing_work_attempt_error_summary_length_check CHECK (error_summary IS NULL OR length(error_summary) <= 64)
);

CREATE INDEX filing_work_items_state_idx ON filing_work_items(state, lease_expires_at, period_end, issuer_id, filing_type);
CREATE INDEX filing_work_attempts_identity_idx ON filing_work_attempts(issuer_id, filing_type, period_end, restatement_version, attempt_number);

CREATE FUNCTION set_filing_work_item_clock() RETURNS trigger AS $$
BEGIN
  NEW.created_at := clock_timestamp();
  NEW.updated_at := NEW.created_at;
  NEW.state_changed_at := NEW.created_at;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION enforce_initial_filing_work_state() RETURNS trigger AS $$
BEGIN
  IF NEW.state <> 'PENDING' OR NEW.attempt_count <> 0 OR NEW.lease_token IS NOT NULL
     OR NEW.lease_owner IS NOT NULL OR NEW.lease_expires_at IS NOT NULL OR NEW.artifact_id IS NOT NULL
     OR NEW.artifact_checksum IS NOT NULL OR NEW.artifact_source_url IS NOT NULL OR NEW.artifact_status IS NOT NULL
     OR NEW.accepted_artifact_id IS NOT NULL OR NEW.accepted_checksum IS NOT NULL
     OR NEW.last_error_class IS NOT NULL OR NEW.last_error_summary IS NOT NULL THEN
    RAISE EXCEPTION 'filing work must be inserted as clean pending work';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION enforce_filing_work_item_transition() RETURNS trigger AS $$
BEGIN
  IF NEW.issuer_id <> OLD.issuer_id OR NEW.filing_type <> OLD.filing_type OR NEW.period_end <> OLD.period_end
     OR NEW.restatement_version <> OLD.restatement_version OR NEW.source_url <> OLD.source_url
     OR NEW.published_at <> OLD.published_at OR NEW.audit_status <> OLD.audit_status
     OR NEW.expected_checksum IS DISTINCT FROM OLD.expected_checksum OR NEW.created_at <> OLD.created_at THEN
    RAISE EXCEPTION 'reviewed filing provenance is immutable';
  END IF;
  IF OLD.state IN ('ACCEPTED','QUARANTINED') THEN
    IF NEW.state <> OLD.state OR NEW.attempt_count <> OLD.attempt_count
       OR NEW.artifact_id IS DISTINCT FROM OLD.artifact_id OR NEW.artifact_checksum IS DISTINCT FROM OLD.artifact_checksum
       OR NEW.artifact_source_url IS DISTINCT FROM OLD.artifact_source_url OR NEW.artifact_status IS DISTINCT FROM OLD.artifact_status
       OR NEW.accepted_artifact_id IS DISTINCT FROM OLD.accepted_artifact_id OR NEW.accepted_checksum IS DISTINCT FROM OLD.accepted_checksum
       OR NEW.last_error_class IS DISTINCT FROM OLD.last_error_class OR NEW.last_error_summary IS DISTINCT FROM OLD.last_error_summary THEN
      RAISE EXCEPTION 'terminal filing work is immutable';
    END IF;
  ELSIF OLD.state = 'RUNNING' AND NEW.state = 'RUNNING' THEN
    IF NEW.artifact_id IS DISTINCT FROM OLD.artifact_id OR NEW.artifact_checksum IS DISTINCT FROM OLD.artifact_checksum
       OR NEW.artifact_source_url IS DISTINCT FROM OLD.artifact_source_url OR NEW.artifact_status IS DISTINCT FROM OLD.artifact_status
       OR NEW.accepted_artifact_id IS DISTINCT FROM OLD.accepted_artifact_id OR NEW.accepted_checksum IS DISTINCT FROM OLD.accepted_checksum
       OR NEW.last_error_class IS DISTINCT FROM OLD.last_error_class OR NEW.last_error_summary IS DISTINCT FROM OLD.last_error_summary
       OR NEW.lease_expires_at <= OLD.lease_expires_at THEN
      RAISE EXCEPTION 'active filing lease fields are immutable';
    END IF;
  ELSIF OLD.state = 'PENDING' AND NEW.state NOT IN ('PENDING','RUNNING') THEN
    RAISE EXCEPTION 'illegal filing work transition';
  ELSIF OLD.state = 'RETRYABLE' AND NEW.state NOT IN ('RETRYABLE','RUNNING') THEN
    RAISE EXCEPTION 'illegal filing work transition';
  ELSIF OLD.state = 'RUNNING' AND NEW.state NOT IN ('RUNNING','ACCEPTED','QUARANTINED','RETRYABLE') THEN
    RAISE EXCEPTION 'illegal filing work transition';
  END IF;
  IF NEW.state = 'RUNNING' THEN
    IF NEW.lease_token IS NULL OR NEW.lease_owner IS NULL OR NEW.lease_expires_at IS NULL THEN
      RAISE EXCEPTION 'running filing work requires a complete lease';
    END IF;
    IF OLD.state IN ('PENDING','RETRYABLE') AND (NEW.attempt_count <> OLD.attempt_count + 1 OR NEW.lease_token = OLD.lease_token) THEN
      RAISE EXCEPTION 'claim must advance attempt and acquire a new lease';
    END IF;
    IF OLD.state = 'RUNNING' AND (NEW.attempt_count <> OLD.attempt_count OR NEW.lease_token <> OLD.lease_token OR NEW.lease_owner <> OLD.lease_owner) THEN
      RAISE EXCEPTION 'running lease identity is immutable';
    END IF;
  ELSE
    IF NEW.lease_token IS NOT NULL OR NEW.lease_owner IS NOT NULL OR NEW.lease_expires_at IS NOT NULL THEN
      RAISE EXCEPTION 'non-running filing work cannot retain a lease';
    END IF;
    IF OLD.state = 'RUNNING' AND NEW.attempt_count <> OLD.attempt_count THEN
      RAISE EXCEPTION 'finalization cannot change attempt count';
    END IF;
    IF OLD.state IN ('PENDING','RETRYABLE') AND NEW.state = OLD.state
       AND (NEW.attempt_count <> OLD.attempt_count OR NEW.artifact_id IS DISTINCT FROM OLD.artifact_id
            OR NEW.artifact_checksum IS DISTINCT FROM OLD.artifact_checksum OR NEW.artifact_source_url IS DISTINCT FROM OLD.artifact_source_url
            OR NEW.artifact_status IS DISTINCT FROM OLD.artifact_status OR NEW.accepted_artifact_id IS DISTINCT FROM OLD.accepted_artifact_id
            OR NEW.accepted_checksum IS DISTINCT FROM OLD.accepted_checksum OR NEW.last_error_class IS DISTINCT FROM OLD.last_error_class
            OR NEW.last_error_summary IS DISTINCT FROM OLD.last_error_summary) THEN
      RAISE EXCEPTION 'unclaimed filing work fields are immutable';
    END IF;
  END IF;
  IF NEW.state = 'RETRYABLE' AND NEW.last_error_summary IS NULL THEN
    RAISE EXCEPTION 'retryable filing work requires a stable reason';
  END IF;
  IF NEW.state IS DISTINCT FROM OLD.state THEN
    NEW.state_changed_at := clock_timestamp();
  ELSE
    NEW.state_changed_at := OLD.state_changed_at;
  END IF;
  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION enforce_filing_work_acceptance() RETURNS trigger AS $$
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

CREATE FUNCTION enforce_filing_work_attempt_insert() RETURNS trigger AS $$
DECLARE item filing_work_items%ROWTYPE;
BEGIN
  SELECT * INTO item FROM filing_work_items
    WHERE issuer_id = NEW.issuer_id AND filing_type = NEW.filing_type AND period_end = NEW.period_end
      AND restatement_version = NEW.restatement_version FOR SHARE;
  IF NEW.finished_at IS NOT NULL OR NEW.outcome_state IS NOT NULL
     OR NOT FOUND OR item.state <> 'RUNNING' OR item.lease_token <> NEW.lease_token
     OR item.attempt_count <> NEW.attempt_number OR item.lease_expires_at <> NEW.lease_expires_at
     OR item.source_url <> NEW.source_url OR item.expected_checksum IS DISTINCT FROM NEW.expected_checksum THEN
    RAISE EXCEPTION 'attempt must match one active filing lease';
  END IF;
  NEW.started_at := clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION enforce_filing_work_attempt_update() RETURNS trigger AS $$
DECLARE item filing_work_items%ROWTYPE;
BEGIN
  IF OLD.finished_at IS NOT NULL THEN
    RAISE EXCEPTION 'completed filing attempts are immutable';
  END IF;
  IF NEW.id <> OLD.id OR NEW.issuer_id <> OLD.issuer_id OR NEW.filing_type <> OLD.filing_type OR NEW.period_end <> OLD.period_end
     OR NEW.restatement_version <> OLD.restatement_version OR NEW.attempt_number <> OLD.attempt_number
     OR NEW.lease_token <> OLD.lease_token OR NEW.worker_id <> OLD.worker_id OR NEW.run_id <> OLD.run_id
     OR NEW.lease_expires_at <> OLD.lease_expires_at OR NEW.source_url <> OLD.source_url
     OR NEW.expected_checksum IS DISTINCT FROM OLD.expected_checksum OR NEW.started_at <> OLD.started_at THEN
    RAISE EXCEPTION 'filing attempt identity is immutable';
  END IF;
  SELECT * INTO item FROM filing_work_items
    WHERE issuer_id = NEW.issuer_id AND filing_type = NEW.filing_type AND period_end = NEW.period_end
      AND restatement_version = NEW.restatement_version;
  IF NOT FOUND OR item.attempt_count <> NEW.attempt_number OR item.state = 'RUNNING'
     OR NEW.outcome_state IS NULL OR NEW.finished_at IS NULL OR NEW.outcome_state <> item.state THEN
    RAISE EXCEPTION 'attempt result is not coupled to its filing work';
  END IF;
  IF NEW.artifact_id IS DISTINCT FROM item.artifact_id OR NEW.artifact_checksum IS DISTINCT FROM item.artifact_checksum
     OR NEW.artifact_source_url IS DISTINCT FROM item.artifact_source_url OR NEW.artifact_status IS DISTINCT FROM item.artifact_status
     OR NEW.error_class IS DISTINCT FROM item.last_error_class OR NEW.error_summary IS DISTINCT FROM item.last_error_summary THEN
    RAISE EXCEPTION 'attempt result snapshot does not match filing work';
  END IF;
  NEW.finished_at := clock_timestamp();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION prevent_filing_work_attempt_delete() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'filing work attempts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION prevent_filing_artifact_drift() RETURNS trigger AS $$
BEGIN
  IF (NEW.parse_status IS DISTINCT FROM OLD.parse_status OR NEW.checksum <> OLD.checksum OR NEW.source_url <> OLD.source_url)
     AND EXISTS (SELECT 1 FROM filing_work_items WHERE artifact_id = OLD.id AND state IN ('ACCEPTED','QUARANTINED')) THEN
    RAISE EXCEPTION 'terminal filing artifact provenance is immutable';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION enforce_filing_work_attempt_completion() RETURNS trigger AS $$
BEGIN
  IF NEW.state = 'RUNNING' AND NOT EXISTS (
    SELECT 1 FROM filing_work_attempts
    WHERE issuer_id = NEW.issuer_id AND filing_type = NEW.filing_type AND period_end = NEW.period_end
      AND restatement_version = NEW.restatement_version AND attempt_number = NEW.attempt_count
      AND lease_token = NEW.lease_token AND finished_at IS NULL
  ) THEN
    RAISE EXCEPTION 'running filing work requires exactly one active attempt';
  END IF;
  IF NEW.state <> 'RUNNING' AND NEW.attempt_count > 0 AND NOT EXISTS (
    SELECT 1 FROM filing_work_attempts
    WHERE issuer_id = NEW.issuer_id AND filing_type = NEW.filing_type AND period_end = NEW.period_end
      AND restatement_version = NEW.restatement_version AND attempt_number = NEW.attempt_count
      AND finished_at IS NOT NULL AND outcome_state = NEW.state
  ) THEN
    RAISE EXCEPTION 'filing work requires exactly one completed attempt';
  END IF;
  RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER filing_work_acceptance_guard BEFORE INSERT OR UPDATE ON filing_work_items
FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_acceptance();
CREATE TRIGGER filing_work_initial_state_guard BEFORE INSERT ON filing_work_items
FOR EACH ROW EXECUTE FUNCTION enforce_initial_filing_work_state();
CREATE TRIGGER filing_work_item_clock_guard BEFORE INSERT ON filing_work_items
FOR EACH ROW EXECUTE FUNCTION set_filing_work_item_clock();
CREATE TRIGGER filing_work_item_transition_guard BEFORE UPDATE ON filing_work_items
FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_item_transition();
CREATE TRIGGER filing_work_attempt_insert_guard BEFORE INSERT ON filing_work_attempts
FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_attempt_insert();
CREATE TRIGGER filing_work_attempt_update_guard BEFORE UPDATE ON filing_work_attempts
FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_attempt_update();
CREATE TRIGGER filing_work_attempt_delete_guard BEFORE DELETE ON filing_work_attempts
FOR EACH ROW EXECUTE FUNCTION prevent_filing_work_attempt_delete();
CREATE TRIGGER filing_work_artifact_drift_guard BEFORE UPDATE OF parse_status,checksum,source_url ON source_artifacts
FOR EACH ROW EXECUTE FUNCTION prevent_filing_artifact_drift();
CREATE CONSTRAINT TRIGGER filing_work_attempt_completion_guard AFTER INSERT OR UPDATE ON filing_work_items
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION enforce_filing_work_attempt_completion();

INSERT INTO schema_migrations(version) VALUES ('007_filing_work_ledger');
COMMIT;
