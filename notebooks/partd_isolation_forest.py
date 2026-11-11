# Databricks notebook source
# MAGIC %md
# MAGIC # Peer-relative anomaly detection for Medicare Part D prescribers
# MAGIC
# MAGIC This notebook runs the same pipeline as `run_all.py`, on Spark instead of DuckDB.
# MAGIC The SQL files in `sql/` are shared, so the record counts here should match a laptop run exactly.
# MAGIC
# MAGIC **Before running**
# MAGIC 1. Add this repository as a Git folder (Workspace, then Create, then Git folder).
# MAGIC 2. Create a volume (Catalog, then `workspace.default`, then Create volume, named `partd`).
# MAGIC 3. Upload the Part D Prescribers by Provider CSV and the OIG `UPDATED.csv` to that volume.
# MAGIC 4. Set the widgets above and run all cells. MLflow runs appear in this notebook's Experiment panel.

# COMMAND ----------

dbutils.widgets.text("partd_path", "/Volumes/workspace/default/partd/mup_dpr_ry26_p04_v20_dy24_npi.csv", "Part D CSV")
dbutils.widgets.text("leie_path", "/Volumes/workspace/default/partd/UPDATED.csv", "LEIE CSV")
dbutils.widgets.text("data_year", "2024", "Data year")
dbutils.widgets.text("out_dir", "/Volumes/workspace/default/partd/output", "Output folder")
dbutils.widgets.dropdown("run_sweep", "yes", ["yes", "no"], "Sensitivity sweep")

# COMMAND ----------

import os
import sys
from pathlib import Path

ROOT = Path(os.getcwd()).parent          # the notebook lives in <repo>/notebooks
sys.path.insert(0, str(ROOT / "src"))

from partd_anomaly.analysis import run_analysis
from partd_anomaly.config import Config
from partd_anomaly.engine import SparkEngine
from partd_anomaly.pipeline import assert_qc, build
from partd_anomaly.tracking import Tracker

cfg = Config(data_year=int(dbutils.widgets.get("data_year")))
OUT = Path(dbutils.widgets.get("out_dir"))
OUT.mkdir(parents=True, exist_ok=True)
cfg

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Build the analysis file and log the row count after every step

# COMMAND ----------

engine = SparkEngine(spark)
counts, qc = build(engine, dbutils.widgets.get("partd_path"), dbutils.widgets.get("leie_path"), cfg, ROOT)
counts.to_csv(OUT / "record_counts.csv", index=False)
qc.to_csv(OUT / "qc_checks.csv", index=False)
display(counts)

# COMMAND ----------

display(qc)
assert_qc(qc)   # stops the notebook if any error-level check is nonzero

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Score, validate, and log to MLflow

# COMMAND ----------

labeled = engine.query("SELECT * FROM s07_labeled")
tracker = Tracker(experiment=None)   # None = this notebook's own experiment
res = run_analysis(labeled, cfg, OUT, tracker, run_sweep=dbutils.widgets.get("run_sweep") == "yes")
display(res["validation"])

# COMMAND ----------

display(res["agreement"])
print(f"Flag stability across seeds (mean pairwise Jaccard): {res['stability']:.3f}")

# COMMAND ----------

if res["sensitivity"] is not None:
    display(res["sensitivity"])

# COMMAND ----------

display(res["flags_by_specialty"])

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Optional. Save the flagged list as a Delta table
# MAGIC The table holds NPIs, so it stays in this workspace and never goes in the repository.

# COMMAND ----------

import pandas as pd

flags = pd.read_csv(OUT / "private" / "flagged_prescribers.csv")
spark.createDataFrame(flags).write.mode("overwrite").saveAsTable("workspace.default.partd_flagged_prescribers")
