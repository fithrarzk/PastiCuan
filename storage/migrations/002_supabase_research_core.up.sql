BEGIN;

ALTER TABLE model_versions DROP CONSTRAINT IF EXISTS model_versions_status_check;
UPDATE model_versions SET status = 'VALIDATED_RESEARCH' WHERE status = 'VALIDATED';
ALTER TABLE model_versions ADD CONSTRAINT model_versions_status_check
  CHECK (status IN ('DRAFT','SHADOW','VALIDATED_RESEARCH','RETIRED'));

CREATE TABLE source_artifacts (
    id uuid PRIMARY KEY,
    provider text NOT NULL,
    source_class text NOT NULL CHECK (source_class IN ('official','licensed','yahoo_fallback')),
    artifact_type text NOT NULL,
    source_url text NOT NULL,
    object_key text,
    checksum text NOT NULL UNIQUE,
    published_at timestamptz,
    retrieved_at timestamptz NOT NULL,
    parser_version text,
    parse_status text NOT NULL CHECK (parse_status IN ('PENDING','ACCEPTED','QUARANTINED')),
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE ingestion_issues (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    artifact_id uuid REFERENCES source_artifacts(id),
    issue_code text NOT NULL,
    severity text NOT NULL CHECK (severity IN ('WARNING','ERROR')),
    detail text NOT NULL,
    status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ACCEPTED','REJECTED')),
    reviewed_at timestamptz,
    review_note text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE validation_runs (
    id uuid PRIMARY KEY,
    model_version_id text NOT NULL REFERENCES model_versions(id),
    input_checksum text NOT NULL,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL CHECK (status IN ('RUNNING','PASSED','FAILED')),
    development_start date,
    development_end date,
    holdout_start date,
    holdout_end date,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    acceptance jsonb NOT NULL DEFAULT '{}'::jsonb,
    output_checksum text,
    UNIQUE (model_version_id, input_checksum)
);

CREATE TABLE quant_research_snapshots (
    id uuid PRIMARY KEY,
    model_version_id text NOT NULL REFERENCES model_versions(id),
    validation_run_id uuid REFERENCES validation_runs(id),
    effective_at timestamptz NOT NULL,
    status text NOT NULL CHECK (status IN ('CANDIDATE','SHADOW','VALIDATED_RESEARCH','REJECTED')),
    schema_version text NOT NULL,
    checksum text NOT NULL UNIQUE,
    payload jsonb NOT NULL,
    approved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((status IN ('SHADOW','VALIDATED_RESEARCH')) = (approved_at IS NOT NULL))
);

CREATE FUNCTION enforce_quant_snapshot_validation() RETURNS trigger AS $$
BEGIN
  IF NEW.status = 'VALIDATED_RESEARCH' AND NOT EXISTS (
    SELECT 1 FROM validation_runs vr
    WHERE vr.id = NEW.validation_run_id
      AND vr.model_version_id = NEW.model_version_id
      AND vr.status = 'PASSED'
  ) THEN
    RAISE EXCEPTION 'VALIDATED_RESEARCH requires a passed validation run for the same model';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER quant_snapshot_validation_guard
BEFORE INSERT OR UPDATE ON quant_research_snapshots
FOR EACH ROW EXECUTE FUNCTION enforce_quant_snapshot_validation();

CREATE INDEX source_artifacts_retrieved_idx ON source_artifacts(provider, retrieved_at);
CREATE INDEX ingestion_issues_open_idx ON ingestion_issues(status, created_at);
CREATE INDEX validation_runs_model_idx ON validation_runs(model_version_id, completed_at);
CREATE INDEX quant_snapshots_approved_idx ON quant_research_snapshots(status, effective_at DESC);

INSERT INTO model_versions
  (id, model_type, formula_version, parameters, code_checksum, status)
VALUES
  ('3.0.0-shadow', 'ANALYSIS_BUNDLE', 'idx-eod-v2', '{}'::jsonb,
   'runtime-version-3.0.0-shadow', 'SHADOW')
ON CONFLICT (id) DO NOTHING;

INSERT INTO schema_migrations(version) VALUES ('002_supabase_research_core');
COMMIT;
