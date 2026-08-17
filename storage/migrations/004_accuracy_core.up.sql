BEGIN;

ALTER TABLE statement_facts
  ADD COLUMN IF NOT EXISTS period_type text,
  ADD COLUMN IF NOT EXISTS duration_class text,
  ADD COLUMN IF NOT EXISTS fiscal_year integer,
  ADD COLUMN IF NOT EXISTS fiscal_quarter integer;

ALTER TABLE statement_facts
  ADD CONSTRAINT statement_facts_period_type_check
    CHECK (period_type IS NULL OR period_type IN ('INSTANT','DURATION')),
  ADD CONSTRAINT statement_facts_duration_class_check
    CHECK (duration_class IS NULL OR duration_class IN ('QTD','YTD','FY','OTHER')),
  ADD CONSTRAINT statement_facts_fiscal_quarter_check
    CHECK (fiscal_quarter IS NULL OR fiscal_quarter BETWEEN 1 AND 4);

ALTER TABLE corporate_actions
  ADD COLUMN IF NOT EXISTS published_at timestamptz,
  ADD COLUMN IF NOT EXISTS source_class text NOT NULL DEFAULT 'official',
  ADD COLUMN IF NOT EXISTS subscription_price numeric,
  ADD COLUMN IF NOT EXISTS validation_status text NOT NULL DEFAULT 'PENDING',
  ADD COLUMN IF NOT EXISTS quarantined_at timestamptz,
  ADD COLUMN IF NOT EXISTS quarantine_reason text;

ALTER TABLE corporate_actions
  ADD CONSTRAINT corporate_actions_source_class_check
    CHECK (source_class IN ('official','licensed','yahoo_fallback')),
  ADD CONSTRAINT corporate_actions_validation_status_check
    CHECK (validation_status IN ('PENDING','ACCEPTED','QUARANTINED')),
  ADD CONSTRAINT corporate_actions_subscription_price_check
    CHECK (subscription_price IS NULL OR subscription_price > 0);

CREATE TABLE provider_runs (
    id uuid PRIMARY KEY,
    provider text NOT NULL,
    capability text NOT NULL,
    source_class text NOT NULL CHECK (source_class IN ('official','licensed','yahoo_fallback')),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED','CIRCUIT_OPEN')),
    attempts integer NOT NULL DEFAULT 1 CHECK (attempts > 0),
    latency_ms integer CHECK (latency_ms IS NULL OR latency_ms >= 0),
    coverage_pct numeric CHECK (coverage_pct IS NULL OR coverage_pct BETWEEN 0 AND 100),
    fallback_from text,
    error_type text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE research_job_runs (
    id uuid PRIMARY KEY,
    job_type text NOT NULL,
    workflow_run_id text,
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    status text NOT NULL CHECK (status IN ('RUNNING','SUCCEEDED','FAILED','DEGRADED')),
    input_checksum text,
    output_checksum text,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    error_type text
);

CREATE TABLE scan_signals (
    snapshot_id uuid NOT NULL REFERENCES scan_research_snapshots(id),
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    signal_session date NOT NULL,
    business_state text NOT NULL,
    entry_state text NOT NULL,
    business_score numeric,
    entry_reference numeric,
    stop_loss numeric,
    target numeric,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, issuer_id)
);

CREATE TABLE signal_outcomes (
    snapshot_id uuid NOT NULL REFERENCES scan_research_snapshots(id),
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    horizon_sessions integer NOT NULL CHECK (horizon_sessions IN (5,20,60,252)),
    evaluated_session date NOT NULL,
    absolute_return numeric,
    benchmark_return numeric,
    excess_return numeric,
    maximum_favorable_excursion numeric,
    maximum_adverse_excursion numeric,
    status text NOT NULL CHECK (status IN ('AVAILABLE','PENDING','SUSPENDED','INSUFFICIENT_DATA')),
    adjustment_version text NOT NULL,
    evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (snapshot_id, issuer_id, horizon_sessions)
);

CREATE TABLE disclosure_events (
    id uuid PRIMARY KEY,
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    event_type text NOT NULL,
    published_at timestamptz NOT NULL,
    available_at timestamptz NOT NULL,
    title text NOT NULL,
    source_url text NOT NULL,
    object_key text,
    checksum text NOT NULL UNIQUE,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE market_research_snapshots (
    id uuid PRIMARY KEY,
    session_date date NOT NULL,
    payload jsonb NOT NULL,
    formula_version text NOT NULL,
    checksum text NOT NULL UNIQUE,
    signature text,
    signing_key_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX provider_runs_capability_idx ON provider_runs(capability, started_at DESC);
CREATE INDEX research_job_runs_type_idx ON research_job_runs(job_type, started_at DESC);
CREATE INDEX scan_signals_pending_idx ON scan_signals(signal_session, issuer_id);
CREATE INDEX signal_outcomes_issuer_idx ON signal_outcomes(issuer_id, evaluated_session DESC);
CREATE INDEX disclosure_events_issuer_idx ON disclosure_events(issuer_id, published_at DESC);

INSERT INTO schema_migrations(version) VALUES ('004_accuracy_core');
COMMIT;
