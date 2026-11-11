-- LEIE step 3. One row per NPI, keeping the earliest qualifying exclusion.
CREATE OR REPLACE TEMP VIEW l03_leie_one_per_npi AS
SELECT npi, excl_date, excl_type
FROM (
    SELECT l.*, ROW_NUMBER() OVER (PARTITION BY npi ORDER BY excl_date, excl_type) AS rn
    FROM l02_leie_after_data_year l
) t
WHERE rn = 1;
