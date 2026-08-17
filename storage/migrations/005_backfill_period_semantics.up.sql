BEGIN;

-- Migration 004 introduced explicit period semantics after some filings had
-- already been imported. Backfill only derived classification fields; source
-- values, availability timestamps and document evidence remain immutable.
UPDATE statement_facts sf
SET period_type = CASE WHEN sf.period_start IS NULL THEN 'INSTANT' ELSE 'DURATION' END,
    duration_class = CASE
      WHEN sf.period_start IS NULL THEN NULL
      WHEN upper(f.filing_type) IN ('ANNUAL','FY','AUDITED')
        OR (sf.period_end - sf.period_start) BETWEEN 330 AND 380 THEN 'FY'
      WHEN upper(f.filing_type) IN ('QTD','DISCRETE') THEN 'QTD'
      WHEN upper(f.filing_type) IN ('Q1','TW1','Q2','TW2','HY','HALF_YEAR','Q3','TW3','9M') THEN 'YTD'
      ELSE 'OTHER'
    END,
    fiscal_year = extract(year FROM sf.period_end)::integer,
    fiscal_quarter = CASE
      WHEN sf.period_start IS NULL THEN NULL
      WHEN upper(f.filing_type) IN ('ANNUAL','FY','AUDITED')
        OR (sf.period_end - sf.period_start) BETWEEN 330 AND 380 THEN 4
      WHEN upper(f.filing_type) IN ('Q1','TW1') THEN 1
      WHEN upper(f.filing_type) IN ('Q2','TW2','HY','HALF_YEAR') THEN 2
      WHEN upper(f.filing_type) IN ('Q3','TW3','9M') THEN 3
      WHEN upper(f.filing_type) IN ('QTD','DISCRETE')
        THEN extract(quarter FROM sf.period_end)::integer
      ELSE NULL
    END
FROM filings f
WHERE f.id = sf.filing_id
  AND (sf.period_type IS NULL
       OR (sf.period_start IS NOT NULL AND sf.duration_class IS NULL)
       OR sf.fiscal_year IS NULL);

INSERT INTO schema_migrations(version) VALUES ('005_backfill_period_semantics');
COMMIT;
