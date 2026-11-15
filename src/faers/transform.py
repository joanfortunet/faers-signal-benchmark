"""Run the steps that turn the raw tables into analysis-ready tables.

Most steps are plain .sql files in the sql/ folder, so they can also be read
(and run by hand) in the DuckDB CLI or a notebook. Drug name normalisation is
a Python step (faers.normalize) because it is easier to read and test.

Usage (from the repository root, after `python -m faers.load`):

    python -m faers.transform
"""

import argparse
import time
from pathlib import Path

import duckdb

from faers.load import DB_PATH
from faers.normalize import build_drug_name_map

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql"
REF_DIR = ROOT / "ref"

# Reference files loaded as tables before the steps run.
REFERENCE_TABLES = {
    "ref_non_clinical_pt": "non_clinical_pt_patterns.csv",
}
STEPS = [
    "02_clean_deduplicate.sql",
    build_drug_name_map,
    "03_classify_events.sql",
    "04_drug_event_counts.sql",
]
SUMMARY_TABLES = [
    "raw_demo", "demo_dedup", "drug_clean", "drug_name_map", "reac_clean", "pt_class",
    "outc_clean", "report_drug_event", "drug_event_counts",
]


def load_reference(con, ref_dir=REF_DIR):
    """Load the small CSV files of ref/ into ref_* tables."""
    for table, filename in REFERENCE_TABLES.items():
        con.execute(
            f"CREATE OR REPLACE TABLE {table} AS "
            "SELECT * FROM read_csv(?, header = true, all_varchar = true)",
            [str(ref_dir / filename)],
        )


def run_step(con, step, sql_dir=SQL_DIR):
    """Run one step: a .sql file name or a Python function taking the connection."""
    if callable(step):
        step(con)
    else:
        con.execute((sql_dir / step).read_text())


def run_all(con, sql_dir=SQL_DIR, ref_dir=REF_DIR):
    load_reference(con, ref_dir)
    for step in STEPS:
        name = step if isinstance(step, str) else step.__name__
        start = time.time()
        run_step(con, step, sql_dir)
        print(f"{name}: done in {time.time() - start:.0f} s", flush=True)


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
