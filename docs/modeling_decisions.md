# Modeling decisions

Every anomaly detection project rests on choices the data cannot settle by itself. This file records each one and the reason for it. Decisions marked **sensitivity candidate** are varied in the sensitivity sweep (`output/sensitivity.csv`) to show how much the results depend on them.

All settings live in `src/partd_anomaly/config.py`. The primary analysis was fixed before looking at the exclusion labels, and the sweep is reported alongside it, never used to pick it. Choosing settings by how well they find excluded providers would overstate how well the model works.

## Data year and outcome

**D1. Both the 2024 and 2023 data years are run, with identical settings.**
2024 is the most recent file. The validation needs time for exclusions to happen after the prescribing, so 2024 has less than two years of follow-up and 2023 has almost three. Running both with the same settings shows whether the results hold up across years.

**D2. The outcome is a later exclusion from Medicare by the HHS Office of Inspector General.**
Public data has no fraud labels. An exclusion dated after the data year is the closest public outcome, and it is prospective, since the model only sees prescribing that happened before it. Someone excluded earlier usually cannot bill Part D at all, so earlier exclusions would mostly measure who is missing from the file. Their count is reported as an info check.

**D3. Two versions of the outcome are reported.**
"Any exclusion" includes license revocations and other reasons that are not about billing. "Fraud-related" keeps the two program crime types, 1128(a)(1) and 1128(a)(3). The broad version has more events and the narrow version is closer to what program integrity work cares about.

**D4. The LEIE is a current snapshot.**
Providers who were excluded and later reinstated drop off the list, so a few true events are missed. This biases lift toward zero, not away from it.

## Who is analyzed

Each step's row count is logged in `output/record_counts.csv`.

**D5. Individual prescribers only.** Organizations prescribe on behalf of many clinicians, so their volumes are not comparable.

**D6. United States addresses only.** Peer groups are built by state.

**D7. Beneficiary count must be published.** CMS blanks counts from 1 to 10. Every per-beneficiary feature needs this count, so these small prescribers are dropped. This also removes the noisiest ratios.

**D8. Specialties with fewer than 100 prescribers nationally are dropped.** A peer comparison needs peers.

## Features

**D9. Ten features, chosen for what program integrity reviewers look at.**
Cost per beneficiary, claims per beneficiary, cost per day of supply, days of supply per claim, brand share, opioid share, long-acting opioid share, antibiotic share, number of beneficiaries (logged), and average beneficiary risk score. The risk score is included so a prescriber with costly patients is not mistaken for a costly prescriber. **Sensitivity candidate** (without risk score).

**D10. Every feature is compared with the prescriber's peers, not with everyone.**
Peers are the same specialty in the same state. When that group has fewer than 50 members, the specialty nationally is used instead. **Sensitivity candidate** (national peers only, and a state minimum of 100).

**D11. Robust z-scores, using the median and MAD of published values.**
Prescribing data is heavily skewed. A mean and standard deviation would be inflated by the very outliers we want to find. Where most of a peer group sits at one value (for example, dermatologists with no opioid claims) the MAD is zero, so the mean absolute deviation is used instead (Iglewicz and Hoaglin, 1993). A peer group with fewer than 20 published values for a feature borrows the national statistics for its specialty. Skewed measures are logged first. Scores are capped at 10 so one extreme value cannot dominate.

**D12. Suppressed values score 0, and never enter the peer statistics.**
CMS blanks brand, opioid, and antibiotic counts from 1 to 10. In 2024 that affects 43% of brand shares and about 25% of opioid and antibiotic shares. A score of 0 means "no evidence either way." The first version filled blanks with the peer median before computing the spread, which stacked identical values at the median and shrank the MAD. Computing the statistics from published values only is the correct method, but on the 2024 file it barely changed which specialties were flagged (see D20).

**D13. Deviations in both directions count.**
An unusually low number of days per claim can mean many short fills, which matters as much as a high one. **Sensitivity candidate** (above-peer deviations only).

## Models

**D14. Isolation Forest with 300 trees, 256 samples per tree, all features.**
These are the settings from the original paper (Liu, Ting, and Zhou, 2008), with more trees than its default of 100 for steadier rankings. **Sensitivity candidates** (100 trees, 1,024 samples, half the features per tree).

**D15. `contamination` is left at "auto".**
In scikit-learn it only moves an internal threshold and does not change the ranking. The share flagged is set separately (D17), so both methods are cut at the same point and compared fairly.

**D16. The baseline is the largest peer z-score.**
This is the rule an analyst would write by hand. If Isolation Forest cannot beat it, the extra complexity is not earning its keep. Agreement between the two is reported, and where they disagree is the interesting part, since the forest can find unusual combinations of measures that are each only moderately high.

**D17. The top 1% of prescribers are flagged for review.**
A program integrity team can only review so many leads. Lift is also reported at other cutoffs in `output/lift_curve.csv`.

**D18. Rows are sorted by NPI before scoring.**
SQL engines return rows in no fixed order, and the forest's random samples depend on row order. Sorting makes every run reproducible on both DuckDB and Spark.

## Privacy

**D19. Results with NPIs stay out of the repository.**
The CMS file is public and names providers, but being statistically unusual is not evidence of wrongdoing. The flagged list is written to `output/private/`, which `.gitignore` excludes. Public outputs are aggregated by specialty, and counts from 1 to 10 are shown as "<11," the same rule CMS uses.

## What the 2024 run showed

**D20. Some specialties are flagged far more often than others, and the reason is real, not a bug.**
Peer comparison removes average differences between specialties, but not differences in the shape of their tails. In 2024, 4.8% of family physicians and 6.1% of pharmacists were flagged, against 0.3% of nurse practitioners. For family physicians, 73% of flags lead with a high antibiotic share, which fits urgent care physicians who enroll as Family Practice. For pharmacists, flags lead with high claims and cost per beneficiary, which fits the very different settings pharmacists prescribe in. Self-reported specialty is a coarse peer group. A rank-based version, which gives every peer group the same tail shape by construction, is in the sensitivity sweep, with the highest specialty flag rate reported for each variant. The primary analysis is not changed after seeing results.

**D21. Rank-based peer scores are the primary method from the 2023 run on.**
This was decided after the 2024 run and before the 2023 run. In 2024, rank-based scores halved the specialty imbalance from D20 and had the highest AUROC of all variants. Making the switch for the next run, rather than rewriting the 2024 results, keeps the 2024 numbers as an honest record of the method chosen in advance. The median and MAD version stays in the sweep for comparison, and `--scaling robust` reproduces the 2024 primary analysis.

