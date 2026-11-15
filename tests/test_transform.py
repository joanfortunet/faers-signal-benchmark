"""Tests for the SQL steps, on tiny hand-made tables with known answers."""

import duckdb
import pytest

from faers.load import TABLES, create_tables
from faers.transform import run_all


def insert(con, table, rows):
    """Insert rows given as dicts; missing columns are left empty."""
    columns = ["quarter"] + TABLES.get(table, ["caseid"])
    for row in rows:
        values = [row.get(column) for column in columns]
        placeholders = ", ".join("?" for _ in columns)
        con.execute(f"INSERT INTO raw_{table} VALUES ({placeholders})", values)


@pytest.fixture
def con():
    """In-memory database with 4 cases:

    case 1: two versions (q1 and q2); only the q2 version must be kept
    case 2: two versions with the same fda_dt; the higher primaryid wins
    case 3: deleted by the FDA; must disappear
    case 4: a normal single-version case
    """
    con = duckdb.connect()
    create_tables(con, rebuild=True)
    insert(con, "demo", [
        {"quarter": "2020q1", "primaryid": "11", "caseid": "1", "fda_dt": "20200110"},
        {"quarter": "2020q2", "primaryid": "12", "caseid": "1", "fda_dt": "20200420"},
        {"quarter": "2020q1", "primaryid": "21", "caseid": "2", "fda_dt": "20200301"},
        {"quarter": "2020q1", "primaryid": "22", "caseid": "2", "fda_dt": "20200301"},
        {"quarter": "2020q1", "primaryid": "31", "caseid": "3", "fda_dt": "20200301"},
        {"quarter": "2020q2", "primaryid": "41", "caseid": "4", "fda_dt": "20200505"},
    ])
    insert(con, "drug", [
        {"quarter": "2020q1", "primaryid": "11", "role_cod": "PS", "prod_ai": "OLD DRUG"},
        {"quarter": "2020q2", "primaryid": "12", "role_cod": "PS", "prod_ai": " semaglutide "},
        {"quarter": "2020q2", "primaryid": "12", "role_cod": "C", "prod_ai": "METFORMIN"},
        {"quarter": "2020q1", "primaryid": "22", "role_cod": "PS", "prod_ai": "SEMAGLUTIDE."},
        {"quarter": "2020q1", "primaryid": "31", "role_cod": "PS", "prod_ai": "SEMAGLUTIDE"},
        {"quarter": "2020q2", "primaryid": "41", "role_cod": "PS", "prod_ai": "",
         "drugname": "Aspirin"},
    ])
    insert(con, "reac", [
        {"quarter": "2020q1", "primaryid": "11", "pt": "Headache"},
        {"quarter": "2020q2", "primaryid": "12", "pt": "Pancreatitis"},
        {"quarter": "2020q2", "primaryid": "12", "pt": "Nausea"},
        {"quarter": "2020q1", "primaryid": "22", "pt": "PANCREATITIS"},
        {"quarter": "2020q1", "primaryid": "31", "pt": "Pancreatitis"},
        {"quarter": "2020q2", "primaryid": "41", "pt": "Nausea"},
    ])
    insert(con, "deleted", [{"quarter": "2020q2", "caseid": "3"}])
    run_all(con)
    yield con
    con.close()


def query(con, sql):
    return con.execute(sql).fetchall()


def test_keeps_latest_version_of_each_case(con):
    kept = query(con, "SELECT caseid, primaryid FROM demo_dedup ORDER BY caseid")
    assert kept == [(1, 12), (2, 22), (4, 41)]


def test_deleted_case_is_removed(con):
    assert query(con, "SELECT COUNT(*) FROM demo_dedup WHERE caseid = 3") == [(0,)]


def test_old_versions_do_not_leak_drugs(con):
    assert query(con, "SELECT COUNT(*) FROM drug_clean WHERE drug = 'OLD DRUG'") == [(0,)]


def test_drug_names_are_normalised(con):
    drugs = query(con, "SELECT DISTINCT drug FROM drug_clean WHERE role_cod = 'PS' ORDER BY 1")
    assert drugs == [("ASPIRIN",), ("SEMAGLUTIDE",)]


def test_reaction_terms_are_case_insensitive(con):
    pts = query(con, "SELECT DISTINCT pt FROM reac_clean ORDER BY 1")
    assert pts == [("nausea",), ("pancreatitis",)]


def test_contingency_table(con):
    # Reports kept: 12 (semaglutide: pancreatitis, nausea),
    #               22 (semaglutide: pancreatitis), 41 (aspirin: nausea)
    row = query(con, """
        SELECT a, b, c, d, n_drug, n_event, n_total
        FROM drug_event_counts
        WHERE drug = 'SEMAGLUTIDE' AND pt = 'pancreatitis'
    """)
    assert row == [(2, 0, 0, 1, 2, 2, 3)]


def test_every_table_adds_up_to_the_total(con):
    bad = query(con, "SELECT COUNT(*) FROM drug_event_counts WHERE a + b + c + d <> n_total")
    assert bad == [(0,)]
