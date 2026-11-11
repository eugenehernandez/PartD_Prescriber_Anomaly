-- Join. Attach the later-exclusion label to the analysis file.
-- A LEFT JOIN on a one-row-per-NPI table, so the row count must not change.
-- Fraud-related types are 1128(a)(1) program crimes and 1128(a)(3) health care fraud felonies.
CREATE OR REPLACE TEMP VIEW s07_labeled AS
SELECT
    f.*,
    CASE WHEN l.npi IS NOT NULL THEN 1 ELSE 0 END                         AS excluded_later,
    CASE WHEN LOWER(l.excl_type) IN ('1128a1', '1128a3') THEN 1 ELSE 0 END AS excluded_later_fraud,
    l.excl_date,
    l.excl_type
FROM s06_features f
LEFT JOIN l03_leie_one_per_npi l
  ON f.npi = l.npi;
