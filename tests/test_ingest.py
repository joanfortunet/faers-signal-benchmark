from faers.ingest import candidate_urls, quarter_range


def test_quarter_range_crosses_year_boundary():
    assert quarter_range("2014q4", "2015q2") == [(2014, 4), (2015, 1), (2015, 2)]


def test_full_window_has_48_quarters():
    assert len(quarter_range("2014q3", "2026q2")) == 48


def test_candidate_urls_try_both_cases():
    urls = candidate_urls(2025, 4)
    assert urls[0].endswith("faers_ascii_2025q4.zip")
    assert urls[1].endswith("faers_ascii_2025Q4.zip")