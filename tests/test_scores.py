"""Tests for faers.scores on a tiny report_drug_event table."""

import duckdb
import pytest

from faers.ebgm import Prior
from faers.scores import counts_as_of, score_pairs

ROWS = [
    # primaryid, init_fda_dt, drug, pt
    (1, "2020-01-10", "X", "rash"),
    (2, "2020-02-10", "X", "rash"),
    (3, "2020-03-10", "Y", "nausea"),
    (4, "2021-01-10", "X", "rash"),
    (5, "2021-01-10", "Y", "rash"),
    (6, "2021-02-10", "Y", "nausea"),
]


@pytest.fixture
def con():
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE report_drug_event "
        "(primaryid BIGINT, init_fda_dt DATE, drug VARCHAR, pt VARCHAR)"
    )
    con.executemany("INSERT INTO report_drug_event VALUES (?, ?, ?, ?)", ROWS)
    yield con
    con.close()


def table(df):
    return {(r.drug, r.pt): (r.a, r.b, r.c, r.d) for r in df.itertuples()}


def test_counts_as_of_uses_only_earlier_reports(con):
    # By the end of 2020 only reports 1-3 exist: X-rash twice, Y-nausea once.
    assert table(counts_as_of(con, "2020-12-31")) == {
        ("X", "rash"): (2, 0, 0, 1),
        ("Y", "nausea"): (1, 0, 0, 2),
    }


def test_counts_as_of_full_window(con):
    counts = table(counts_as_of(con, "2030-01-01"))
    assert counts[("X", "rash")] == (3, 0, 1, 2)
    assert all(sum(cells) == 6 for cells in counts.values())


def test_score_pairs_adds_every_method(con):
    counts = counts_as_of(con, "2030-01-01")
    prior = Prior(alpha1=0.2, beta1=0.1, alpha2=2.0, beta2=4.0, p=1 / 3)
    scored, used = score_pairs(counts, prior)
    assert used is prior
    for column in ["expected", "prr", "ror_lower", "ic025", "ebgm", "eb05",
                   "prr_signal", "ror_signal", "bcpnn_signal", "ebgm_signal"]:
        assert column in scored.columns
    assert len(scored) == len(counts)
