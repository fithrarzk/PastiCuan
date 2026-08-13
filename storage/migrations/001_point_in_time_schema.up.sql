BEGIN;

CREATE TABLE schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE issuers (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ticker text NOT NULL UNIQUE,
    legal_name text NOT NULL,
    sector text NOT NULL,
    issuer_type text NOT NULL DEFAULT 'general',
    currency char(3) NOT NULL,
    active_from date NOT NULL,
    active_to date
);

CREATE TABLE index_constituents (
    index_code text NOT NULL,
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    effective_from date NOT NULL,
    effective_to date NOT NULL,
    source_url text NOT NULL,
    checksum text NOT NULL,
    PRIMARY KEY (index_code, issuer_id, effective_from),
    CHECK (effective_to >= effective_from)
);

CREATE TABLE market_sessions (
    exchange text NOT NULL DEFAULT 'IDX',
    session_date date NOT NULL,
    opens_at timestamptz,
    closes_at timestamptz,
    status text NOT NULL CHECK (status IN ('SCHEDULED','COMPLETED','HOLIDAY','HALTED')),
    PRIMARY KEY (exchange, session_date)
);

CREATE TABLE market_bars (
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    session_date date NOT NULL,
    version integer NOT NULL DEFAULT 1,
    open numeric NOT NULL CHECK (open > 0),
    high numeric NOT NULL CHECK (high > 0),
    low numeric NOT NULL CHECK (low > 0),
    close numeric NOT NULL CHECK (close > 0),
    volume numeric NOT NULL CHECK (volume >= 0),
    currency char(3) NOT NULL,
    available_at timestamptz NOT NULL,
    source_class text NOT NULL CHECK (source_class IN ('official','licensed','yahoo_fallback')),
    source_url text,
    checksum text NOT NULL,
    quarantined_at timestamptz,
    quarantine_reason text,
    PRIMARY KEY (issuer_id, session_date, version),
    CHECK (high >= GREATEST(open, low, close)),
    CHECK (low <= LEAST(open, high, close))
);

CREATE TABLE corporate_actions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    action_type text NOT NULL CHECK (action_type IN ('SPLIT','DIVIDEND','RIGHTS','DELISTING')),
    ex_date date NOT NULL,
    payable_date date,
    ratio numeric,
    cash_amount numeric,
    currency char(3),
    available_at timestamptz NOT NULL,
    source_url text NOT NULL,
    checksum text NOT NULL,
    version integer NOT NULL DEFAULT 1,
    UNIQUE (issuer_id, action_type, ex_date, version)
);

CREATE TABLE filings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    filing_type text NOT NULL,
    period_end date NOT NULL,
    published_at timestamptz,
    available_at timestamptz NOT NULL,
    consolidated boolean NOT NULL,
    audit_status text NOT NULL,
    restatement_version integer NOT NULL DEFAULT 1,
    source_url text NOT NULL,
    object_key text NOT NULL,
    document_checksum text NOT NULL,
    quarantined_at timestamptz,
    quarantine_reason text,
    UNIQUE (issuer_id, filing_type, period_end, restatement_version)
);

CREATE TABLE statement_facts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    filing_id bigint NOT NULL REFERENCES filings(id),
    taxonomy text NOT NULL,
    concept text NOT NULL,
    normalized_concept text NOT NULL,
    period_start date,
    period_end date NOT NULL,
    published_at timestamptz,
    available_at timestamptz NOT NULL,
    value numeric NOT NULL,
    currency char(3),
    scale integer NOT NULL DEFAULT 0,
    unit text NOT NULL,
    consolidated boolean NOT NULL,
    audit_status text NOT NULL,
    source_url text NOT NULL,
    document_checksum text NOT NULL,
    restatement_version integer NOT NULL,
    UNIQUE (filing_id, concept, period_start, period_end, unit)
);

CREATE TABLE shares_history (
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    effective_from date NOT NULL,
    effective_to date,
    period_end_shares numeric NOT NULL CHECK (period_end_shares > 0),
    weighted_average_shares numeric CHECK (weighted_average_shares > 0),
    available_at timestamptz NOT NULL,
    source_url text NOT NULL,
    checksum text NOT NULL,
    PRIMARY KEY (issuer_id, effective_from)
);

CREATE TABLE fx_rates (
    rate_date date NOT NULL,
    base_currency char(3) NOT NULL,
    quote_currency char(3) NOT NULL,
    rate numeric NOT NULL CHECK (rate > 0),
    rate_type text NOT NULL,
    available_at timestamptz NOT NULL,
    source_url text NOT NULL,
    checksum text NOT NULL,
    PRIMARY KEY (rate_date, base_currency, quote_currency, rate_type)
);

CREATE TABLE policy_rates (
    observation_date date NOT NULL,
    rate_name text NOT NULL,
    annual_rate numeric NOT NULL,
    available_at timestamptz NOT NULL,
    source_url text NOT NULL,
    checksum text NOT NULL,
    PRIMARY KEY (observation_date, rate_name)
);

CREATE TABLE model_versions (
    id text PRIMARY KEY,
    model_type text NOT NULL,
    formula_version text NOT NULL,
    parameters jsonb NOT NULL,
    code_checksum text NOT NULL,
    status text NOT NULL CHECK (status IN ('DRAFT','SHADOW','VALIDATED','RETIRED')),
    shadow_started_at timestamptz,
    validated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE analysis_snapshots (
    id uuid PRIMARY KEY,
    issuer_id bigint NOT NULL REFERENCES issuers(id),
    as_of timestamptz NOT NULL,
    horizon text NOT NULL,
    analysis_version text NOT NULL REFERENCES model_versions(id),
    bundle jsonb NOT NULL,
    data_quality_grade text NOT NULL,
    action_label text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (issuer_id, as_of, horizon, analysis_version)
);

CREATE TABLE derived_metrics (
    snapshot_id uuid NOT NULL REFERENCES analysis_snapshots(id) ON DELETE CASCADE,
    metric_name text NOT NULL,
    value numeric,
    status text NOT NULL CHECK (status IN ('AVAILABLE','INSUFFICIENT_DATA','NOT_MEANINGFUL','QUARANTINED')),
    unit text,
    data_window text,
    formula_version text NOT NULL,
    source_values jsonb NOT NULL,
    PRIMARY KEY (snapshot_id, metric_name)
);

CREATE TABLE signals (
    snapshot_id uuid NOT NULL REFERENCES analysis_snapshots(id) ON DELETE CASCADE,
    horizon text NOT NULL,
    signal_time timestamptz NOT NULL,
    earliest_execution_time timestamptz NOT NULL,
    state text NOT NULL,
    PRIMARY KEY (snapshot_id, horizon),
    CHECK (earliest_execution_time > signal_time)
);

CREATE TABLE alert_deliveries (
    ticker text NOT NULL,
    signal_date date NOT NULL,
    horizon text NOT NULL,
    model_version text NOT NULL,
    channel text NOT NULL,
    status text NOT NULL,
    sent_at timestamptz,
    error text,
    PRIMARY KEY (ticker, signal_date, horizon, model_version, channel)
);

CREATE INDEX market_bars_asof_idx ON market_bars (issuer_id, available_at, session_date);
CREATE INDEX facts_asof_idx ON statement_facts (filing_id, normalized_concept, available_at, period_end);
CREATE INDEX constituents_asof_idx ON index_constituents (index_code, effective_from, effective_to);

INSERT INTO schema_migrations(version) VALUES ('001_point_in_time_schema');
COMMIT;

