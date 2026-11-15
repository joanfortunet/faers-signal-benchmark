"""Load the raw FAERS quarterly ASCII files into a DuckDB database.

Every table is loaded "as is": all columns are kept as text (VARCHAR) and a
'quarter' column is added so we always know which file a row came from.
Cleaning, typing and deduplication happen later, in SQL (see sql/).

The load is incremental: quarters already in the database are skipped, and
each quarter is loaded inside a transaction, so an interrupted run never
leaves a half-loaded quarter behind.

Usage (from the repository root, with the 'faers' conda env active):

    python -m faers.load                          # every new quarter in data/raw
    python -m faers.load --quarters 2025q3 2025q4 # only some quarters
    python -m faers.load --rebuild                # drop everything and start again
"""

import argparse
import re
from pathlib import Path

import duckdb

RAW_DIR = Path("data/raw")
DB_PATH = Path("data/faers_warehouse.duckdb")

# Columns we expect in each file (identical from 2014 Q3 to 2026 Q2).
# Listing them explicitly means the load fails loudly if the FDA changes them.
TABLES = {
    "demo": [
        "primaryid", "caseid", "caseversion", "i_f_code", "event_dt", "mfr_dt",
        "init_fda_dt", "fda_dt", "rept_cod", "auth_num", "mfr_num", "mfr_sndr",
        "lit_ref", "age", "age_cod", "age_grp", "sex", "e_sub", "wt", "wt_cod",
        "rept_dt", "to_mfr", "occp_cod", "reporter_country", "occr_country",
    ],
    "drug": [
        "primaryid", "caseid", "drug_seq", "role_cod", "drugname", "prod_ai",
        "val_vbm", "route", "dose_vbm", "cum_dose_chr", "cum_dose_unit", "dechal",
        "rechal", "lot_num", "exp_dt", "nda_num", "dose_amt", "dose_unit",
        "dose_form", "dose_freq",
    ],
    "reac": ["primaryid", "caseid", "pt", "drug_rec_act"],
    "outc": ["primaryid", "caseid", "outc_cod"],
    "indi": ["primaryid", "caseid", "indi_drug_seq", "indi_pt"],
    "ther": ["primaryid", "caseid", "dsg_drug_seq", "start_dt", "end_dt", "dur", "dur_cod"],
}

QUARTER_DIR = re.compile(r"^faers_ascii_(\d{4}q[1-4])$")


def list_quarters(raw_dir):
    """Return {'2014q3': Path(...), ...} for every fully downloaded quarter folder."""
    quarters = {}
    for folder in sorted(raw_dir.iterdir()):
        match = QUARTER_DIR.match(folder.name)
        if folder.is_dir() and match:
            quarters[match.group(1)] = folder
    return quarters


def find_table_file(quarter_dir, table):
    """Find e.g. ASCII/DEMO14Q3.txt. Folder and file name case varies by year."""
    for path in quarter_dir.rglob("*.txt"):
        if path.parent.name.lower() == "ascii" and path.name.lower().startswith(table):
            return path
    raise FileNotFoundError(f"No {table.upper()} file in {quarter_dir}")


def find_deleted_files(quarter_dir):
    """Lists of deleted case ids (only exist from 2019 Q1). Names vary by year."""
    return sorted(
        path for path in quarter_dir.rglob("*.txt") if path.parent.name.lower() == "deleted"
    )


def csv_options(columns):
    """read_csv options for the '$'-separated FAERS files (everything as text)."""
    column_spec = ", ".join(f"'{name}': 'VARCHAR'" for name in columns)
    return (
        "auto_detect = false, delim = '$', header = true, quote = '', escape = '', "
        f"columns = {{{column_spec}}}, "
        "null_padding = true, ignore_errors = true, store_rejects = true"
    )


def create_tables(con, rebuild=False):
    """Create the raw tables and the load log (dropping old ones if rebuild)."""
    create = "CREATE OR REPLACE TABLE" if rebuild else "CREATE TABLE IF NOT EXISTS"
    for table, columns in TABLES.items():
        column_defs = ", ".join(f"{name} VARCHAR" for name in columns)
        con.execute(f"{create} raw_{table} (quarter VARCHAR, {column_defs})")
    con.execute(f"{create} raw_deleted (quarter VARCHAR, caseid VARCHAR)")
    con.execute(
        f"{create} load_log ("
        "quarter VARCHAR, table_name VARCHAR, file VARCHAR, "
        "rows_loaded BIGINT, rows_rejected BIGINT)"
    )


def loaded_quarters(con):
    """Quarters already in the database."""
    return {row[0] for row in con.execute("SELECT DISTINCT quarter FROM load_log").fetchall()}


def load_quarter(con, quarter, folder):
    """Load every table of one quarter, all or nothing."""
    con.execute("BEGIN TRANSACTION")
    try:
        for table in TABLES:
            path = find_table_file(folder, table)
            loaded, rejected = load_table_file(con, quarter, table, path)
            log(con, quarter, table, path, loaded, rejected)
        for path in find_deleted_files(folder):
            log(con, quarter, "deleted", path, load_deleted_file(con, quarter, path), 0)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def check_header(path, expected):
    """Stop if the file's header is not the column list we expect."""
    with open(path, encoding="latin-1") as file:
        header = file.readline().strip().lower().rstrip("$").split("$")
    if header != expected:
        raise ValueError(f"Unexpected columns in {path}: {header}")


def load_table_file(con, quarter, table, path):
    """Append one file to raw_<table>. Return (rows_loaded, rows_rejected)."""
    columns = TABLES[table]
    check_header(path, columns)
    before = con.execute(f"SELECT COUNT(*) FROM raw_{table}").fetchone()[0]
    con.execute(
        f"INSERT INTO raw_{table} "
        f"SELECT '{quarter}' AS quarter, * FROM read_csv(?, {csv_options(columns)})",
        [str(path)],
    )
    after = con.execute(f"SELECT COUNT(*) FROM raw_{table}").fetchone()[0]
    # reject_errors keeps the bad lines of every file read; count only this one.
    rejected = con.execute(
        "SELECT COUNT(DISTINCT line) FROM reject_errors WHERE scan_id IN "
        "(SELECT scan_id FROM reject_scans WHERE file_path = ?)",
        [str(path)],
    ).fetchone()[0]
    return after - before, rejected


def load_deleted_file(con, quarter, path):
    """Append one list of deleted case ids. Blank or non-numeric lines are skipped."""
    before = con.execute("SELECT COUNT(*) FROM raw_deleted").fetchone()[0]
    con.execute(
        "INSERT INTO raw_deleted "
        "SELECT ?, trim(caseid) FROM read_csv(?, header = false, delim = '$', "
        "quote = '', columns = {'caseid': 'VARCHAR'}) "
        "WHERE regexp_full_match(trim(caseid), '[0-9]+')",
        [quarter, str(path)],
    )
    return con.execute("SELECT COUNT(*) FROM raw_deleted").fetchone()[0] - before


def log(con, quarter, table, path, loaded, rejected):
    con.execute(
        "INSERT INTO load_log VALUES (?, ?, ?, ?, ?)",
        [quarter, table, path.name, loaded, rejected],
    )


def load_all(raw_dir, db_path, only=None, rebuild=False):
    """Load every new quarter (or only the ones in 'only'). Return the quarters loaded."""
    quarters = list_quarters(raw_dir)
    if only:
        missing = set(only) - set(quarters)
        if missing:
            raise SystemExit(f"Not downloaded: {', '.join(sorted(missing))}")
        quarters = {q: quarters[q] for q in only}

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    create_tables(con, rebuild)
    done = loaded_quarters(con)
    loaded = []
    for quarter, folder in quarters.items():
        if quarter in done:
            print(f"{quarter}: already loaded, skipping", flush=True)
            continue
        load_quarter(con, quarter, folder)
        loaded.append(quarter)
        print(f"{quarter}: loaded", flush=True)
    con.close()
    return loaded


def main():
    parser = argparse.ArgumentParser(description="Load raw FAERS files into DuckDB.")
    parser.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--quarters", nargs="+", help="e.g. 2025q3 2025q4 (default: all)")
    parser.add_argument("--rebuild", action="store_true", help="drop and reload everything")
    args = parser.parse_args()

    loaded = load_all(args.raw_dir, args.db, args.quarters, args.rebuild)
    print(f"\nDone: {len(loaded)} new quarters loaded into {args.db}")


if __name__ == "__main__":
    main()
