"""SQL engine adapter.

The SQL in sql/ is written once and runs on two engines:
  * DuckDB on a laptop (run_all.py)
  * Spark SQL in Databricks (notebooks/)

Only file registration differs between them. Everything after that is plain SQL
that both engines accept: CREATE OR REPLACE TEMP VIEW, CASE, COALESCE, TRY_CAST,
window functions, and SUM(CASE ...) instead of dialect-specific FILTER clauses.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


def read_sql_file(path: str | Path, params: dict | None = None) -> str:
    """Read a .sql file, fill @placeholders, and drop full-line comments."""
    sql = Path(path).read_text(encoding="utf-8")
    for key, value in (params or {}).items():
        sql = sql.replace(f"@{key}", str(value))
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return "\n".join(lines)


def split_statements(sql: str) -> list[str]:
    parts = re.split(r";\s*(?:\n|$)", sql)
    return [p.strip() for p in parts if p.strip()]


class Engine:
    """Minimal common interface over DuckDB and Spark."""

    name = "base"

    def register_csv(self, view: str, path: str) -> None:
        raise NotImplementedError

    def execute(self, sql: str) -> None:
        raise NotImplementedError

    def query(self, sql: str) -> pd.DataFrame:
        raise NotImplementedError

    def columns(self, view: str) -> list[str]:
        return [c.lower() for c in self.query(f"SELECT * FROM {view} LIMIT 0").columns]

    def count(self, view: str) -> int:
        return int(self.query(f"SELECT COUNT(*) AS n FROM {view}")["n"].iloc[0])

    def run_file(self, path: str | Path, params: dict | None = None) -> None:
        for stmt in split_statements(read_sql_file(path, params)):
            self.execute(stmt)

    def query_file(self, path: str | Path, params: dict | None = None) -> pd.DataFrame:
        return self.query(read_sql_file(path, params))


class DuckDBEngine(Engine):
    name = "duckdb"

    def __init__(self, database: str = ":memory:"):
        import duckdb

        self.con = duckdb.connect(database)

    def register_csv(self, view: str, path: str) -> None:
        # all_varchar keeps NPIs, ZIPs, and suppression flags exactly as published.
        # The build SQL casts the numeric columns it needs with TRY_CAST.
        self.con.execute(
            f"CREATE OR REPLACE TEMP VIEW {view} AS "
            f"SELECT * FROM read_csv('{path}', header = true, all_varchar = true)"
        )

    def execute(self, sql: str) -> None:
        self.con.execute(sql)

    def query(self, sql: str) -> pd.DataFrame:
        return self.con.execute(sql).df()


class SparkEngine(Engine):
    name = "spark"

    def __init__(self, spark):
        self.spark = spark

    def register_csv(self, view: str, path: str) -> None:
        # inferSchema is off for the same reason as all_varchar above.
        (
            self.spark.read.option("header", True)
            .option("inferSchema", False)
            .csv(path)
            .createOrReplaceTempView(view)
        )

    def execute(self, sql: str) -> None:
        self.spark.sql(sql)

    def query(self, sql: str) -> pd.DataFrame:
        return self.spark.sql(sql).toPandas()
