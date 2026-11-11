"""MLflow logging that degrades gracefully.

In Databricks, MLflow is built in and runs appear under the notebook's experiment.
On a laptop, runs go to ./mlruns (view them with `mlflow ui`). If MLflow is not
installed, the pipeline still runs and simply skips logging.
"""

from __future__ import annotations

import contextlib


class Tracker:
    def __init__(self, experiment: str | None = None, enabled: bool = True):
        self.mlflow = None
        if not enabled:
            return
        import os
        # Git is optional. Without it MLflow only loses the commit ID, so skip its warning.
        os.environ.setdefault("GIT_PYTHON_REFRESH", "quiet")
        try:
            import mlflow
        except ImportError:
            print("MLflow not installed. Runs will not be logged.")
            return
        self.mlflow = mlflow
        if not experiment:
            return
        try:
            mlflow.set_experiment(experiment)
        except Exception:
            # A slim MLflow install cannot open the default local database.
            # Fall back to a plain folder store in ./mlruns.
            try:
                import os
                from pathlib import Path
                os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
                mlflow.set_tracking_uri(Path("mlruns").resolve().as_uri())
                mlflow.set_experiment(experiment)
            except Exception as e:  # pragma: no cover
                print(f"MLflow logging is off ({type(e).__name__}: {e})")
                self.mlflow = None

    @contextlib.contextmanager
    def run(self, name: str, nested: bool = False):
        if self.mlflow is None:
            yield None
            return
        with self.mlflow.start_run(run_name=name, nested=nested) as r:
            yield r

    def params(self, d: dict) -> None:
        if self.mlflow:
            self.mlflow.log_params({k: str(v)[:500] for k, v in d.items()})

    def metrics(self, d: dict, prefix: str = "") -> None:
        if self.mlflow:
            clean = {f"{prefix}{k}": float(v) for k, v in d.items()
                     if isinstance(v, (int, float)) and v == v}  # drops NaN
            self.mlflow.log_metrics(clean)

    def artifact(self, path: str) -> None:
        if self.mlflow:
            self.mlflow.log_artifact(path)

    def tags(self, d: dict) -> None:
        if self.mlflow:
            self.mlflow.set_tags(d)
