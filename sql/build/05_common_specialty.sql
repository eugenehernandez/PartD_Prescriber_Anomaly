-- Step 5. Keep specialties with at least @min_specialty_n prescribers nationally.
-- A peer comparison is not meaningful for a specialty with a handful of members.
CREATE OR REPLACE TEMP VIEW s05_common_specialty AS
SELECT *
FROM (
    SELECT c.*, COUNT(*) OVER (PARTITION BY specialty) AS specialty_n
    FROM s04_clean c
) t
WHERE specialty_n >= @min_specialty_n;
