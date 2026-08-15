BEGIN;

CREATE TABLE scan_research_snapshots (
    id uuid PRIMARY KEY,
    session_date date NOT NULL,
    universe text NOT NULL CHECK (universe = 'LQ45'),
    mode text NOT NULL CHECK (mode IN ('PRIMARY','DEGRADED','UNAVAILABLE')),
    model_status text NOT NULL CHECK (model_status = 'SHADOW'),
    quant_snapshot_id uuid REFERENCES quant_research_snapshots(id),
    universe_coverage_pct numeric NOT NULL CHECK (universe_coverage_pct BETWEEN 0 AND 100),
    schema_version text NOT NULL,
    formula_version text NOT NULL,
    checksum text NOT NULL UNIQUE,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    published_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((mode = 'PRIMARY') = (quant_snapshot_id IS NOT NULL))
);

CREATE INDEX scan_snapshots_latest_idx
  ON scan_research_snapshots(session_date DESC, published_at DESC);

CREATE FUNCTION prevent_scan_snapshot_mutation() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'scan research snapshots are immutable';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER scan_snapshot_immutable_guard
BEFORE UPDATE OR DELETE ON scan_research_snapshots
FOR EACH ROW EXECUTE FUNCTION prevent_scan_snapshot_mutation();

INSERT INTO schema_migrations(version) VALUES ('003_scan_research_snapshots');
COMMIT;
