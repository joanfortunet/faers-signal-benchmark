"""Tests for MGPS / EBGM."""

import numpy as np
import pytest
from scipy import stats

from faers.ebgm import Prior, ebgm, fit_prior, posterior_quantile

PRIOR = Prior(alpha1=0.2, beta1=0.1, alpha2=2.0, beta2=4.0, p=1 / 3)


def test_single_gamma_prior_has_closed_form():
    # With p = 1 the posterior is Gamma(alpha + a, beta + E), whose geometric
    # mean and percentiles are known exactly.
    prior = Prior(alpha1=1.0, beta1=1.0, alpha2=5.0, beta2=5.0, p=1 - 1e-12)
    a, e = np.array([4.0]), np.array([2.0])
    result = ebgm(a, e, prior)
    posterior = stats.gamma(a=1 + 4, scale=1 / (1 + 2))
    assert result["eb05"][0] == pytest.approx(posterior.ppf(0.05), rel=1e-6)
    assert result["eb95"][0] == pytest.approx(posterior.ppf(0.95), rel=1e-6)
    assert result["ebgm"][0] == pytest.approx(np.exp(posterior.expect(np.log)), rel=1e-6)


def test_posterior_quantiles_are_ordered():
    a, e = np.array([1.0, 10.0, 100.0]), np.array([0.5, 1.0, 10.0])
    q05 = posterior_quantile(0.05, a, e, PRIOR)
    q50 = posterior_quantile(0.50, a, e, PRIOR)
    q95 = posterior_quantile(0.95, a, e, PRIOR)
    assert np.all(q05 < q50) and np.all(q50 < q95)


def test_small_counts_are_shrunk_large_counts_are_not():
    # Same raw ratio a / E = 10, with very different amounts of evidence.
    a = np.array([1.0, 1000.0])
    e = np.array([0.1, 100.0])
    result = ebgm(a, e, PRIOR)
    assert result["ebgm"][0] < 5  # one report: pulled far below 10
    assert result["ebgm"][1] == pytest.approx(10, rel=0.02)  # lots of data: ~ a / E
    assert result["signal"].tolist() == [False, True]


def test_fit_prior_recovers_simulated_parameters():
    rng = np.random.default_rng(0)
    true = Prior(alpha1=0.5, beta1=1.0, alpha2=5.0, beta2=1.5, p=0.6)
    n = 60_000
    first = rng.random(n) < true.p
    lam = np.where(
        first,
        rng.gamma(true.alpha1, 1 / true.beta1, n),
        rng.gamma(true.alpha2, 1 / true.beta2, n),
    )
    e = rng.uniform(0.5, 5, n)
    a = rng.poisson(lam * e)
    keep = a > 0  # like drug_event_counts, only pairs with at least one report
    fitted = fit_prior(a[keep], e[keep])
    assert fitted.p == pytest.approx(true.p, abs=0.08)
    assert fitted.alpha2 / fitted.beta2 == pytest.approx(true.alpha2 / true.beta2, rel=0.1)


def _numeric_posterior(a, e, prior, grid):
    """Unnormalised posterior density of lambda on a grid, computed from scratch:
    prior density (mixture of two gammas) x Poisson likelihood."""
    prior_density = prior.p * stats.gamma.pdf(grid, prior.alpha1, scale=1 / prior.beta1) + (
        1 - prior.p
    ) * stats.gamma.pdf(grid, prior.alpha2, scale=1 / prior.beta2)
    return prior_density * stats.poisson.pmf(a, grid * e)


@pytest.mark.parametrize("a,e", [(1, 0.2), (3, 0.5), (10, 1.0), (50, 20.0)])
def test_closed_form_matches_numerical_integration(a, e):
    """Independent check of the posterior formulas (a substitute for openEBGM)."""
    prior = Prior(alpha1=0.3, beta1=0.2, alpha2=2.5, beta2=2.0, p=0.4)
    grid = np.exp(np.linspace(-12, 6, 400_001))  # log-spaced lambda grid
    density = _numeric_posterior(a, e, prior, grid) * grid  # change of variable to log
    weights = density / density.sum()
    cdf = np.cumsum(weights)
    expected_ebgm = np.exp(np.sum(weights * np.log(grid)))
    expected_eb05 = grid[np.searchsorted(cdf, 0.05)]
    expected_eb95 = grid[np.searchsorted(cdf, 0.95)]

    result = ebgm(np.array([a]), np.array([e]), prior)
    assert result["ebgm"][0] == pytest.approx(expected_ebgm, rel=1e-3)
    assert result["eb05"][0] == pytest.approx(expected_eb05, rel=1e-3)
    assert result["eb95"][0] == pytest.approx(expected_eb95, rel=1e-3)
