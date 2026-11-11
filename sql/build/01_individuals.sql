-- Step 1. Keep individual prescribers.
-- Organizations (Prscrbr_Ent_Cd = 'O') prescribe on behalf of many clinicians,
-- so their volumes are not comparable to a single prescriber's.
CREATE OR REPLACE TEMP VIEW s01_individuals AS
SELECT *
FROM raw_partd
WHERE TRIM(prscrbr_ent_cd) = 'I';
