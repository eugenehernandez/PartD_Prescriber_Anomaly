-- Step 2. Keep prescribers with a United States practice address.
-- Peer groups are built by state, so a foreign address has no peer group.
CREATE OR REPLACE TEMP VIEW s02_us_address AS
SELECT *
FROM s01_individuals
WHERE TRIM(prscrbr_cntry) = 'US'
  AND prscrbr_state_abrvtn IS NOT NULL;
