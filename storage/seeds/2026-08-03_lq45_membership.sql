-- One-time bootstrap for the LQ45 composition effective 2026-08-03 through
-- 2026-10-30, reported from IDX announcement Peng-00148/BEI.POP/07-2026.
--
-- This seed deliberately does not invent issuer fundamentals. For issuers not
-- already present, ticker is used as a temporary display name and sector is
-- UNCLASSIFIED. A later reviewed issuer-master import may enrich those fields.
-- active_from is the first date known to this database, not an asserted IPO date.

BEGIN;

CREATE TEMP TABLE seed_lq45_membership (
    ticker text PRIMARY KEY
) ON COMMIT DROP;

INSERT INTO seed_lq45_membership(ticker) VALUES
  ('AADI'), ('ADMR'), ('ADRO'), ('AKRA'), ('AMMN'),
  ('AMRT'), ('ANTM'), ('ASII'), ('BBCA'), ('BBNI'),
  ('BBRI'), ('BBTN'), ('BMRI'), ('BRPT'), ('BUMI'),
  ('CPIN'), ('CUAN'), ('DEWA'), ('EMTK'), ('ESSA'),
  ('EXCL'), ('GOTO'), ('HRTA'), ('ICBP'), ('INCO'),
  ('INDF'), ('INDY'), ('INKP'), ('ISAT'), ('ITMG'),
  ('JPFA'), ('KLBF'), ('MAPI'), ('MBMA'), ('MDKA'),
  ('MEDC'), ('NCKL'), ('PGAS'), ('PGEO'), ('PTBA'),
  ('SCMA'), ('TLKM'), ('UNTR'), ('UNVR'), ('WIFI');

INSERT INTO issuers(ticker, legal_name, sector, currency, active_from)
SELECT ticker, ticker, 'UNCLASSIFIED', 'IDR', DATE '2026-08-03'
FROM seed_lq45_membership
ON CONFLICT (ticker) DO NOTHING;

INSERT INTO index_constituents(
    index_code, issuer_id, effective_from, effective_to, source_url, checksum
)
SELECT
    'LQ45',
    issuers.id,
    DATE '2026-08-03',
    DATE '2026-10-30',
    'https://www.idx.co.id/id/data-pasar/data-saham/indeks-saham/',
    'idx-peng-00148-bei-pop-07-2026:' || seed_lq45_membership.ticker
FROM seed_lq45_membership
JOIN issuers USING (ticker)
ON CONFLICT (index_code, issuer_id, effective_from) DO UPDATE SET
    effective_to = EXCLUDED.effective_to,
    source_url = EXCLUDED.source_url,
    checksum = EXCLUDED.checksum;

DO $$
DECLARE
    seeded_count integer;
BEGIN
    SELECT count(*) INTO seeded_count
    FROM index_constituents
    WHERE index_code = 'LQ45'
      AND effective_from <= DATE '2026-08-16'
      AND effective_to >= DATE '2026-08-16';
    IF seeded_count <> 45 THEN
        RAISE EXCEPTION 'Expected exactly 45 effective LQ45 constituents; found %', seeded_count;
    END IF;
END;
$$;

COMMIT;

SELECT count(*) AS effective_lq45_members
FROM index_constituents
WHERE index_code = 'LQ45'
  AND effective_from <= DATE '2026-08-16'
  AND effective_to >= DATE '2026-08-16';
