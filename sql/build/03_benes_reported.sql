-- Step 3. Keep prescribers whose beneficiary count is published.
-- CMS suppresses counts from 1 to 10. Every per-beneficiary feature needs it.
CREATE OR REPLACE TEMP VIEW s03_benes_reported AS
SELECT *
FROM s02_us_address
WHERE TRY_CAST(REPLACE(REPLACE(TRIM(tot_benes), ',', ''), '$', '') AS DOUBLE) > 0;
