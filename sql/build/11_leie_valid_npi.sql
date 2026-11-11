-- LEIE step 1. Keep exclusions that carry an NPI.
-- Older exclusions predate the NPI and are recorded as 0000000000.
CREATE OR REPLACE TEMP VIEW l01_leie_valid_npi AS
SELECT
    TRY_CAST(npi AS BIGINT)       AS npi,
    TRY_CAST(excldate AS INT)     AS excl_date,
    excltype                      AS excl_type
FROM raw_leie
WHERE TRY_CAST(npi AS BIGINT) > 0
  AND TRY_CAST(excldate AS INT) IS NOT NULL;
