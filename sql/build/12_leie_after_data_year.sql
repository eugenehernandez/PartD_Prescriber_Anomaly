-- LEIE step 2. Keep exclusions dated after the Part D data year (@data_year_end).
-- This makes the check prospective: the model only sees prescribing that happened
-- before the exclusion. Someone excluded earlier usually cannot bill Part D at all.
CREATE OR REPLACE TEMP VIEW l02_leie_after_data_year AS
SELECT *
FROM l01_leie_valid_npi
WHERE excl_date > @data_year_end;
