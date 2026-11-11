-- Step 4. Keep rows with a specialty and positive totals, and cast the columns we use.
-- Suppressed values arrive as blanks and become NULL through TRY_CAST.
-- Some CMS downloads format numbers as "1,234" or "$1,234.56", so commas and
-- dollar signs are removed before casting.
CREATE OR REPLACE TEMP VIEW s04_clean AS
SELECT
    TRY_CAST(REPLACE(TRIM(prscrbr_npi), '.0', '') AS BIGINT)        AS npi,
    TRIM(prscrbr_type)                                               AS specialty,
    TRIM(prscrbr_state_abrvtn)                                       AS state,
    TRY_CAST(REPLACE(REPLACE(TRIM(tot_clms), ',', ''), '$', '') AS DOUBLE) AS tot_clms,
    TRY_CAST(REPLACE(REPLACE(TRIM(tot_30day_fills), ',', ''), '$', '') AS DOUBLE) AS tot_30day_fills,
    TRY_CAST(REPLACE(REPLACE(TRIM(tot_drug_cst), ',', ''), '$', '') AS DOUBLE) AS tot_drug_cst,
    TRY_CAST(REPLACE(REPLACE(TRIM(tot_day_suply), ',', ''), '$', '') AS DOUBLE) AS tot_day_suply,
    TRY_CAST(REPLACE(REPLACE(TRIM(tot_benes), ',', ''), '$', '') AS DOUBLE) AS tot_benes,
    TRY_CAST(REPLACE(REPLACE(TRIM(brnd_tot_clms), ',', ''), '$', '') AS DOUBLE) AS brnd_tot_clms,
    TRY_CAST(REPLACE(REPLACE(TRIM(opioid_tot_clms), ',', ''), '$', '') AS DOUBLE) AS opioid_tot_clms,
    TRY_CAST(REPLACE(REPLACE(TRIM(opioid_la_tot_clms), ',', ''), '$', '') AS DOUBLE) AS opioid_la_tot_clms,
    TRY_CAST(REPLACE(REPLACE(TRIM(antbtc_tot_clms), ',', ''), '$', '') AS DOUBLE) AS antbtc_tot_clms,
    TRY_CAST(REPLACE(REPLACE(TRIM(bene_avg_risk_scre), ',', ''), '$', '') AS DOUBLE) AS bene_avg_risk_scre
FROM s03_benes_reported
WHERE prscrbr_type IS NOT NULL
  AND TRIM(prscrbr_type) <> ''
  AND TRY_CAST(REPLACE(TRIM(prscrbr_npi), '.0', '') AS BIGINT) IS NOT NULL
  AND TRY_CAST(REPLACE(REPLACE(TRIM(tot_clms), ',', ''), '$', '') AS DOUBLE) > 0
  AND TRY_CAST(REPLACE(REPLACE(TRIM(tot_drug_cst), ',', ''), '$', '') AS DOUBLE) > 0
  AND TRY_CAST(REPLACE(REPLACE(TRIM(tot_day_suply), ',', ''), '$', '') AS DOUBLE) > 0;
