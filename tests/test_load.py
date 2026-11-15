"""Tests for faers.load, using small fake quarter folders."""

import duckdb

from faers.load import TABLES, load_all


def make_quarter(raw_dir, quarter, ascii_name="ascii", bad_drug_line=False, deleted=None):
    """Write a fake quarter with one report in every table."""
    folder = raw_dir / f"faers_ascii_{quarter}" / ascii_name
    folder.mkdir(parents=True)
    suffix = quarter[2:].upper()  # '2020q1' -> '20Q1'
    for table, columns in TABLES.items():
        lines = ["$".join(columns), "$".join(["1"] * len(columns))]
        if table == "drug" and bad_drug_line:
            lines.append("$".join(["2"] * (len(columns) + 3)))  # too many columns
        (folder / f"{table.upper()}{suffix}.txt").write_text("\n".join(lines) + "\n")
    if deleted:
        deleted_dir = folder.parent / "Deleted"
        deleted_dir.mkdir()
        (deleted_dir / f"DELETE{suffix}.txt").write_text(" \n" + "\n".join(deleted) + "\n")


def read(db_path, sql):
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.execute(sql).fetchall()


def test_loads_every_table_and_logs_rejected_lines(tmp_path):
    make_quarter(tmp_path, "2020q1", bad_drug_line=True, deleted=["123", "456"])
    make_quarter(tmp_path, "2020q2", ascii_name="ASCII")
    db = tmp_path / "test.duckdb"

    assert load_all(tmp_path, db) == ["2020q1", "2020q2"]
    assert read(db, "SELECT COUNT(*) FROM raw_demo") == [(2,)]
    assert read(db, "SELECT caseid FROM raw_deleted ORDER BY 1") == [("123",), ("456",)]
    rejected = read(db, "SELECT quarter, rows_rejected FROM load_log WHERE table_name = 'drug'")
    assert sorted(rejected) == [("2020q1", 1), ("2020q2", 0)]


def test_second_run_only_loads_new_quarters(tmp_path):
    make_quarter(tmp_path, "2020q1")
    db = tmp_path / "test.duckdb"
    load_all(tmp_path, db)

    make_quarter(tmp_path, "2020q2")
    assert load_all(tmp_path, db) == ["2020q2"]
    assert read(db, "SELECT COUNT(*) FROM raw_demo") == [(2,)]
