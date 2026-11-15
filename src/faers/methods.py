"""Disproportionality methods for signal detection.

Every function takes the cells of the 2x2 table as numpy arrays (or numbers)
and works on all drug-event pairs at once:

                     event        other events
    drug               a               b
    other drugs        c               d

with N = a + b + c + d and E = (a + b)(a + c) / N, the number of reports
expected for the pair if the drug and the event were independent.

Methods
-------
- PRR   Proportional Reporting Ratio (Evans et al., 2001)
- ROR   Reporting Odds Ratio (van Puijenbroek et al., 2002)
- BCPNN Information Component with the WHO-UMC shrinkage (Norén et al., 2006, 2013)
- MGPS  Empirical Bayes Geometric Mean, EBGM (DuMouchel, 1999) -> see faers.ebgm

Each method returns a point estimate, a lower bound, and a boolean "signal"
column following the threshold most used in the literature.
"""

import numpy as np

Z_95 = 1.959964  # two-sided 95 % normal quantile


def _as_float(*arrays):
    return [np.asarray(x, dtype=float) for x in arrays]


def expected(a, b, c, d):
    """Expected count under independence: E = (a + b)(a + c) / N."""
    a, b, c, d = _as_float(a, b, c, d)
    n = a + b + c + d
    return (a + b) * (a + c) / n


def prr(a, b, c, d):
    """PRR with its 95 % CI, chi-square (Yates) and the Evans signal criterion.

    Evans et al. (2001): signal if a >= 3, PRR >= 2 and chi-square >= 4.
    Returns a dict of arrays: prr, prr_lower, prr_upper, chi2, signal.
    """
    a, b, c, d = _as_float(a, b, c, d)
    n = a + b + c + d
    with np.errstate(divide="ignore", invalid="ignore"):
        value = (a / (a + b)) / (c / (c + d))
        se_log = np.sqrt(1 / a - 1 / (a + b) + 1 / c - 1 / (c + d))
        lower = np.exp(np.log(value) - Z_95 * se_log)
        upper = np.exp(np.log(value) + Z_95 * se_log)
        chi2 = (
            n * np.maximum(np.abs(a * d - b * c) - n / 2, 0) ** 2
            / ((a + b) * (c + d) * (a + c) * (b + d))
        )
    signal = (a >= 3) & (value >= 2) & (chi2 >= 4)
    return {"prr": value, "prr_lower": lower, "prr_upper": upper, "chi2": chi2, "signal": signal}


def ror(a, b, c, d):
    """ROR with its 95 % CI. Signal if a >= 3 and the lower bound is > 1.

    When a cell is 0 the odds ratio is undefined, so 0.5 is added to every
    cell of that pair only (Haldane-Anscombe correction).
    Returns a dict of arrays: ror, ror_lower, ror_upper, signal.
    """
    a, b, c, d = _as_float(a, b, c, d)
    has_zero = (a == 0) | (b == 0) | (c == 0) | (d == 0)
    a_, b_, c_, d_ = (np.where(has_zero, x + 0.5, x) for x in (a, b, c, d))
    value = (a_ * d_) / (b_ * c_)
    se_log = np.sqrt(1 / a_ + 1 / b_ + 1 / c_ + 1 / d_)
    lower = np.exp(np.log(value) - Z_95 * se_log)
    upper = np.exp(np.log(value) + Z_95 * se_log)
    signal = (a >= 3) & (lower > 1)
    return {"ror": value, "ror_lower": lower, "ror_upper": upper, "signal": signal}


def bcpnn(a, b, c, d):
    """BCPNN Information Component (IC) with shrinkage. Signal if IC025 > 0.

    IC = log2((a + 0.5) / (E + 0.5)). The +0.5 pulls pairs with very few
    reports towards IC = 0 ("no association"). IC025 is the lower end of the
    95 % credibility interval, with the closed-form approximation of
    Norén et al. (2013): IC025 = IC - 3.3 (a + 0.5)^-1/2 - 2 (a + 0.5)^-3/2.
    Returns a dict of arrays: ic, ic025, ic975, signal.
    """
    a, b, c, d = _as_float(a, b, c, d)
    e = expected(a, b, c, d)
    ic = np.log2((a + 0.5) / (e + 0.5))
    ic025 = ic - 3.3 * (a + 0.5) ** -0.5 - 2 * (a + 0.5) ** -1.5
    ic975 = ic + 2.4 * (a + 0.5) ** -0.5 - 0.5 * (a + 0.5) ** -1.5
    return {"ic": ic, "ic025": ic025, "ic975": ic975, "signal": ic025 > 0}
