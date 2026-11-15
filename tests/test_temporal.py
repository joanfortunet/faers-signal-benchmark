"""Tests for the quarter-by-quarter replay used for time to detection."""

import duckdb
import pandas as pd
import pytest

from faers.ebgm import Prior
from faers.scores import counts_as_of
from faers.temporal import (
    build_quarterly_counts,
    counts_until,
    first_signal_dates,
    lead_times,
    summarise_lead_times,
)

PRIOR = Prior(alpha1=0.2, beta1=0.1, alpha2=2.0, beta2=4.0, p=1 / 3)


@pytest.fixture
def con():
    """Drug X gets a burst of 'rash' reports in 2021; drug Y is background noise."""
    rows, pid = [], 0
    for quarter_start in pd.date_range("2020-01-01", "2021-12-31", freq="QS"):
        for _ in range(40):  # background: Y with various events
            pid += 1
            rows.append((pid, quarter_start + pd.Timedelta(days=10), "Y", f"event{pid % 20}"))
        for _ in range(2):  # X with nausea, every quarter
            pid += 1
            rows.append((pid, quarter_start + pd.Timedelta(days=20), "X", "nausea"))
        if quarter_start.year == 2021:  # X-rash appears in 2021
            for _ in range(4):
                pid += 1
                rows.append((pid, quarter_start + pd.Timedelta(days=30), "X", "rash"))
    con = duckdb.connect()
    con.execute(
        "CREATE TABLE report_drug_event "
        "(primaryid BIGINT, init_fda_dt DATE, drug VARCHAR, pt VARCHAR)"
    )
    con.executemany("INSERT INTO report_drug_event VALUES (?, ?, ?, ?)", rows)
    build_quarterly_counts(con)
    yield con
    con.close()


def test_cumulative_counts_match_direct_recount(con):
    cutoff = "2021-06-30"
    direct = counts_as_of(con, cutoff).set_index(["drug", "pt"]).sort_index()
    cumulative = counts_until(con, cutoff).set_index(["drug", "pt"]).sort_index()
    pd.testing.assert_frame_equal(direct, cumulative, check_dtype=False)


def test_signal_appears_after_the_burst_starts(con):
    pairs = pd.DataFrame({"drug": ["X"], "pt": ["rash"]})
    quarter_ends = pd.date_range("2020-03-31", "2021-12-31", freq="QE")
    first = first_signal_dates(con, pairs, quarter_ends, prior=PRIOR, verbose=False)
    assert first.loc[0, "first_prr"] == pd.Timestamp("2021-03-31")

    labels = pd.DataFrame({"drug": ["X"], "pt": ["rash"],
                           "label_date": [pd.Timestamp("2022-03-31")]})
    leads = lead_times(first, labels)
    assert leads.loc[0, "lead_prr"] == pytest.approx(12, abs=0.5)  # one year earlier
    summary = summarise_lead_times(leads).set_index("method")
    assert summary.loc["prr", "detected_before_label"] == 1


def test_replay_pair_follows_the_counts(con):
    from faers.temporal import replay_pair

    quarter_ends = pd.date_range("2020-03-31", "2021-12-31", freq="QE")
    history = replay_pair(con, "X", "rash", quarter_ends, PRIOR)
    assert history.quarter_end.min() == pd.Timestamp("2021-03-31")  # first rash report
    assert history.a.tolist() == [4, 8, 12, 16]
    assert history.eb05.is_monotonic_increasing
