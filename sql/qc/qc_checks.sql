-- QC checks. Each row is one check:
--   n_flagged = records that fail or are worth a look, n_base = what they are counted out of.
-- "error" checks must be zero. "info" checks describe the data and belong in the write-up.

SELECT 'NPI is unique in the analysis file' AS check_name, 'error' AS severity,
       COUNT(*) - COUNT(DISTINCT npi) AS n_flagged, COUNT(*) AS n_base
FROM s06_features

UNION ALL
SELECT 'label join did not change the row count', 'error',
       ABS((SELECT COUNT(*) FROM s07_labeled) - (SELECT COUNT(*) FROM s06_features)),
       (SELECT COUNT(*) FROM s06_features)

UNION ALL
SELECT 'raw NPIs that are not 10 digits', 'error',
       SUM(CASE WHEN LENGTH(TRIM(prscrbr_npi)) <> 10 THEN 1 ELSE 0 END), COUNT(*)
FROM raw_partd

UNION ALL
SELECT 'shares above 1 (brand, opioid, antibiotic)', 'error',
       SUM(CASE WHEN brand_share > 1 OR opioid_share > 1 OR antibiotic_share > 1 THEN 1 ELSE 0 END),
       COUNT(*)
FROM s06_features

UNION ALL
SELECT 'brand share suppressed (scored 0, no evidence either way)', 'info',
       SUM(CASE WHEN brand_share IS NULL THEN 1 ELSE 0 END), COUNT(*)
FROM s06_features

UNION ALL
SELECT 'opioid share suppressed or blank (scored 0, no evidence either way)', 'info',
       SUM(CASE WHEN opioid_share IS NULL THEN 1 ELSE 0 END), COUNT(*)
FROM s06_features

UNION ALL
SELECT 'antibiotic share suppressed or blank (scored 0, no evidence either way)', 'info',
       SUM(CASE WHEN antibiotic_share IS NULL THEN 1 ELSE 0 END), COUNT(*)
FROM s06_features

UNION ALL
SELECT 'beneficiary risk score missing (scored 0, no evidence either way)', 'info',
       SUM(CASE WHEN bene_risk_score IS NULL THEN 1 ELSE 0 END), COUNT(*)
FROM s06_features

UNION ALL
SELECT 'analysis prescribers excluded after the data year (label)', 'info',
       SUM(excluded_later), COUNT(*)
FROM s07_labeled

UNION ALL
SELECT 'analysis prescribers excluded after the data year for fraud (1128a1, 1128a3)', 'info',
       SUM(excluded_later_fraud), COUNT(*)
FROM s07_labeled

UNION ALL
SELECT 'LEIE NPIs excluded after the data year found among all raw prescribers', 'info',
       (SELECT COUNT(*) FROM l03_leie_one_per_npi l
         WHERE l.npi IN (SELECT TRY_CAST(prscrbr_npi AS BIGINT) FROM raw_partd)),
       (SELECT COUNT(*) FROM l03_leie_one_per_npi)

UNION ALL
SELECT 'prescribers with an exclusion dated on or before the data year end', 'info',
       (SELECT COUNT(DISTINCT f.npi) FROM s06_features f
          JOIN l01_leie_valid_npi l ON f.npi = l.npi
         WHERE l.excl_date <= @data_year_end),
       (SELECT COUNT(*) FROM s06_features)
