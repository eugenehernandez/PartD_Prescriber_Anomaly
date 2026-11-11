-- Step 6. Per-prescriber features. No rows are removed here.
-- Shares are NULL when CMS suppressed the numerator. The Python step fills them
-- with the peer-group median, which gives that feature a peer-relative score of 0.
CREATE OR REPLACE TEMP VIEW s06_features AS
SELECT
    npi,
    specialty,
    state,
    tot_benes,
    tot_clms,
    tot_drug_cst,
    tot_drug_cst / tot_benes                      AS cost_per_bene,
    tot_clms / tot_benes                          AS clms_per_bene,
    tot_drug_cst / tot_day_suply                  AS cost_per_day,
    tot_day_suply / tot_clms                      AS days_per_clm,
    brnd_tot_clms / tot_clms                      AS brand_share,
    opioid_tot_clms / tot_clms                    AS opioid_share,
    opioid_la_tot_clms / tot_clms                 AS la_opioid_share,
    antbtc_tot_clms / tot_clms                    AS antibiotic_share,
    bene_avg_risk_scre                            AS bene_risk_score
FROM s05_common_specialty;
