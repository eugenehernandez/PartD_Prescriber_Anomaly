"""Build the analysis file with SQL and log the row count after every step."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import Config
from .engine import Engine

# (view created, sql file, plain-language description of what the step removes)
PARTD_STEPS = [
    ("raw_partd", None, "Part D Prescribers by Provider file as published"),
    ("s01_individuals", "01_individuals.sql", "keep individual prescribers, drop organizations"),
    ("s02_us_address", "02_us_address.sql", "keep United States practice addresses"),
    ("s03_benes_reported", "03_benes_reported.sql", "drop rows with a suppressed beneficiary count (1 to 10)"),
    ("s04_clean", "04_clean.sql", "drop rows with no specialty or zero totals"),
    ("s05_common_specialty", "05_common_specialty.sql", "drop specialties below the national minimum"),
    ("s06_features", "06_features.sql", "compute features (no rows removed)"),
]
LEIE_STEPS = [
    ("raw_leie", None, "LEIE exclusion list as published"),
    ("l01_leie_valid_npi", "11_leie_valid_npi.sql", "keep exclusions recorded with an NPI"),
    ("l02_leie_after_data_year", "12_leie_after_data_year.sql", "keep exclusions dated after the data year"),
    ("l03_leie_one_per_npi", "13_leie_one_per_npi.sql", "one row per NPI (earliest qualifying exclusion)"),
]
JOIN_STEPS = [
    ("s07_labeled", "20_labeled.sql", "attach later-exclusion label (row count must not change)"),
]

REQUIRED_PARTD_COLUMNS = {
    "prscrbr_npi", "prscrbr_ent_cd", "prscrbr_cntry", "prscrbr_state_abrvtn", "prscrbr_type",
    "tot_clms", "tot_30day_fills", "tot_drug_cst", "tot_day_suply", "tot_benes",
    "brnd_tot_clms", "opioid_tot_clms", "opioid_la_tot_clms", "antbtc_tot_clms",
    "bene_avg_risk_scre",
}
REQUIRED_LEIE_COLUMNS = {"npi", "excldate", "excltype"}


def check_columns(engine: Engine, view: str, required: set) -> None:
    missing = sorted(required - set(engine.columns(view)))
    if missing:
        raise ValueError(
            f"{view} is missing columns {missing}. CMS sometimes renames columns between "
            "releases, so compare the file header with the data dictionary."
        )


NUMERIC_CHECK = ["prscrbr_npi", "tot_clms", "tot_drug_cst", "tot_day_suply", "tot_benes"]


def diagnose_numeric(engine: Engine, view: str = "s03_benes_reported") -> None:
    """Print columns whose non-blank values do not convert to numbers, with examples.
    Called when a cleaning step removes every row, which means a format changed."""
    print("\n  Step 4 removed every row. Checking how the numeric columns are formatted:")
    for c in NUMERIC_CHECK:
        q = (f"SELECT {c} AS v FROM {view} WHERE {c} IS NOT NULL AND TRIM({c}) <> '' "
             f"AND TRY_CAST(REPLACE(REPLACE(TRIM({c}), ',', ''), '$', '') AS DOUBLE) IS NULL LIMIT 3")
        bad = engine.query(q)["v"].tolist()
        examples = engine.query(f"SELECT {c} AS v FROM {view} LIMIT 3")["v"].tolist()
        status = f"NOT NUMERIC, e.g. {bad}" if bad else "ok"
        print(f"    {c:<16} {status:<50} first values {examples}")
    t = engine.query(f"SELECT prscrbr_type AS v FROM {view} LIMIT 3")["v"].tolist()
    print(f"    {'prscrbr_type':<16} first values {t}")


def build(engine: Engine, partd_path: str, leie_path: str, cfg: Config, repo_root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run every SQL step. Returns (record_counts, qc_checks)."""
    sql_dir = repo_root / "sql"
    params = {"data_year_end": cfg.data_year_end, "min_specialty_n": cfg.min_specialty_n}

    engine.register_csv("raw_partd", partd_path)
    engine.register_csv("raw_leie", leie_path)
    check_columns(engine, "raw_partd", REQUIRED_PARTD_COLUMNS)
    check_columns(engine, "raw_leie", REQUIRED_LEIE_COLUMNS)

    rows = []
    for source, steps in (("Part D", PARTD_STEPS), ("LEIE", LEIE_STEPS), ("Join", JOIN_STEPS)):
        prev = None
        for view, sql_file, desc in steps:
            if sql_file:
                engine.run_file(sql_dir / "build" / sql_file, params)
            n = engine.count(view)
            rows.append({
                "source": source,
                "step": view,
                "description": desc,
                "rows": n,
                "rows_removed": (prev - n) if prev is not None else None,
            })
            print(f"  {view:<26} {n:>12,}")
            if view == "s04_clean" and n == 0:
                diagnose_numeric(engine)
                raise RuntimeError("No rows survived step 4. Send the lines above to fix the format.")
            prev = n
    # The join is compared with the features view, not with the last LEIE step.
    rows[-1]["rows_removed"] = engine.count("s06_features") - rows[-1]["rows"]

    counts = pd.DataFrame(rows)
    qc = engine.query_file(sql_dir / "qc" / "qc_checks.sql", params)
    qc["pct_flagged"] = (100 * qc["n_flagged"] / qc["n_base"].where(qc["n_base"] > 0)).round(2)
    return counts, qc


def assert_qc(qc: pd.DataFrame) -> None:
    failed = qc[(qc["severity"] == "error") & (qc["n_flagged"].fillna(0) > 0)]
    if len(failed):
        raise RuntimeError("Error-level QC checks failed:\n" + failed.to_string(index=False))
