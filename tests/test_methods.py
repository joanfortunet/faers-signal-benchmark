"""Tests for the disproportionality methods, with values computed by hand."""

import numpy as np
import pytest

from faers.methods import bcpnn, expected, prr, ror

# A strong signal: 10 of the 100 reports of the drug mention the event,
# against 100 of the 9,900 reports of all other drugs.
A, B, C, D = 10, 90, 100, 9800


def test_expected_count():
    assert expected(A, B, C, D) == pytest.approx(100 * 110 / 10_000)


def test_prr_value_and_signal():
    result = prr(A, B, C, D)
    assert result["prr"] == pytest.approx(0.1 / (100 / 9900))  # 9.9
    assert result["prr_lower"] < result["prr"] < result["prr_upper"]
    assert result["signal"]


def test_prr_needs_three_reports():
    # Same ratio as before but only 2 reports: never a signal under Evans' rule.
    assert not prr(2, 18, 100, 9800)["signal"]


def test_ror_value_and_signal():
    result = ror(A, B, C, D)
    assert result["ror"] == pytest.approx(10 * 9800 / (90 * 100))
    assert result["ror_lower"] > 1
    assert result["signal"]


def test_ror_handles_empty_cell():
    # b = 0: every report of the drug mentions the event. Without the
    # correction the ROR would be infinite.
    result = ror(5, 0, 100, 9895)
    assert np.isfinite(result["ror"])


def test_bcpnn_information_component():
    e = 100 * 110 / 10_000
    result = bcpnn(A, B, C, D)
    assert result["ic"] == pytest.approx(np.log2((10 + 0.5) / (e + 0.5)))
    assert result["ic025"] < result["ic"] < result["ic975"]
    assert result["signal"]


def test_bcpnn_is_zero_when_observed_equals_expected():
    # a = E = 1: no disproportionality at all.
    assert bcpnn(1, 99, 99, 9801)["ic"] == pytest.approx(0, abs=1e-9)


def test_methods_work_on_arrays():
    a = np.array([10, 1])
    b = np.array([90, 99])
    c = np.array([100, 99])
    d = np.array([9800, 9801])
    assert prr(a, b, c, d)["signal"].tolist() == [True, False]
    assert ror(a, b, c, d)["signal"].tolist() == [True, False]
    assert bcpnn(a, b, c, d)["signal"].tolist() == [True, False]
