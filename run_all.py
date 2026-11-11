"""Run the full pipeline on a laptop with DuckDB.

    python run_all.py --year 2024

The data files are found automatically in the folder that holds this repo
(any subfolder). The Part D file is matched by its data year, for example
mup_dpr_ry26_p04_v20_dy24_npi.csv for 2024, and the exclusion list by the name
UPDATED.csv. Use --partd and --leie to point at files somewhere else.

Outputs land in output/<year>/. The flagged prescriber list with NPIs goes to
output/<year>/private/, which .gitignore keeps out of the repo.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from partd_anomaly.analysis import run_analysis  # noqa: E402
from partd_anomaly.config import Config  # noqa: E402
from partd_anomaly.engine import DuckDBEngine  # noqa: E402
from partd_anomaly.pipeline import assert_qc, build  # noqa: E402
from partd_anomaly.tracking import Tracker  # noqa: E402


DATA_ROOT = ROOT.parent


def find_file(patterns: list, what: str) -> str:
    hits = sorted({p for pat in patterns for p in DATA_ROOT.rglob(pat) if ROOT not in p.parents})
    if not hits:
        sys.exit(f"Could not find {what} ({' or '.join(patterns)}) anywhere under {DATA_ROOT}. "
                 "Download it into that folder, or pass its path with --partd or --leie.")
    if len(hits) > 1:
        print(f"Found more than one {what}, using {hits[0]}")
    return str(hits[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--partd", help="Part D Prescribers by Provider CSV (found automatically if omitted)")
    ap.add_argument("--leie", help="OIG LEIE UPDATED.csv (found automatically if omitted)")
    ap.add_argument("--year", type=int, default=Config.data_year, help="data year of the Part D file")
    ap.add_argument("--out", help="output folder (default output/<year>)")
    ap.add_argument("--scaling", choices=["rank", "robust"], default=Config.scaling,
                    help="peer scoring for the primary analysis (2024 was run with robust)")
    ap.add_argument("--no-sweep", action="store_true", help="skip the sensitivity sweep")
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    yy = str(args.year)[-2:]
    # CMS names the file differently depending on which download button is used.
    partd = args.partd or find_file(
        [f"mup_dpr_*_dy{yy}_npi.csv", f"Medicare_Part_D_Prescribers_by_Provider_{args.year}.csv"],
        f"Part D file for {args.year}")
    leie = args.leie or find_file(["UPDATED.csv"], "LEIE exclusion list")
    print(f"Part D file  {partd}\nLEIE file    {leie}\n")

    cfg = Config(data_year=args.year, scaling=args.scaling)
    out = Path(args.out) if args.out else ROOT / "output" / str(args.year)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("Building the analysis file")
    engine = DuckDBEngine()
    counts, qc = build(engine, partd, leie, cfg, ROOT)
    counts.to_csv(out / "record_counts.csv", index=False)
    qc.to_csv(out / "qc_checks.csv", index=False)
    print(qc[["check_name", "severity", "n_flagged", "n_base"]].to_string(index=False))
    assert_qc(qc)

    print("\nScoring")
    labeled = engine.query("SELECT * FROM s07_labeled")
    tracker = Tracker(experiment="partd-isolation-forest", enabled=not args.no_mlflow)
    res = run_analysis(labeled, cfg, out, tracker, run_sweep=not args.no_sweep)

    cols = ["outcome", "method", "n_flagged", "excluded_among_flagged", "precision_at_k_pct",
            "lift_at_k", "auroc", "p_value_vs_random"]
    print("\nValidation against later OIG exclusion")
    print(res["validation"][cols].round(3).to_string(index=False))
    print(f"\nFlag stability across seeds (Jaccard): {res['stability']:.3f}")
    if res["sensitivity"] is not None:
        print("\nSensitivity")
        print(res["sensitivity"].to_string(index=False))
    print(f"\nDone in {time.time() - t0:.0f} s. Outputs are in {out}")


if __name__ == "__main__":
    main()
