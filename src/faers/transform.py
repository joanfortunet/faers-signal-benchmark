"""Run the SQL steps that turn the raw tables into analysis-ready tables.

Each step is a plain .sql file in the sql/ folder, so it can also be read
(and run by hand) in the DuckDB CLI or a notebook.

Usage (from the repository root, after `python -m faers.load`):

    python -m faers.transform
"""

import argparse
import time
from pathlib import Path

import duckdb

from faers.load import DB_PATH

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
STEPS = [
    "02_clean_deduplicate.sql",
    "03_drug_event_counts.sql",
]
SUMMARY_TABLES = [
    "raw_demo", "demo_dedup", "drug_clean", "reac_clean", "outc_clean",
    "report_drug_event", "drug_event_counts",
]


def run_step(con, filename, sql_dir=SQL_DIR):
    """Execute every statement of one .sql file."""
    con.execute((sql_dir / filename).read_text())


def run_all(con, sql_dir=SQL_DIR):
    for filename in STEPS:
        start = time.time()
        run_step(con, filename, sql_dir)
        print(f"{filename}: done in {time.time() - start:.0f} s", flush=True)


def summary(con):
    """Row count of every table produced, to check the pipeline at a glance."""
    for table in SUMMARY_TABLES:
        n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:<20}{n:>14,}")


def main():
    parser = argparse.ArgumentParser(description="Clean, deduplicate and count FAERS data.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    con = duckdb.connect(str(args.db))
    run_all(con)
    print()
    summary(con)
    con.close()


if __name__ == "__main__":
    main()
