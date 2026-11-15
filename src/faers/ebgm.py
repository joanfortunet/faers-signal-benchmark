"""MGPS / EBGM: the Empirical Bayes method used by the FDA (DuMouchel, 1999).

Idea
----
For each drug-event pair we observe a reports and expect E under
independence. The "true" reporting ratio lambda = a / E is very noisy when
a is small. MGPS assumes that the lambdas of all pairs come from a common
prior, a mixture of two gamma distributions:

    lambda ~ p * Gamma(alpha1, beta1) + (1 - p) * Gamma(alpha2, beta2)

The five prior parameters are estimated from the data themselves (that is
the "empirical" in Empirical Bayes): with a ~ Poisson(lambda * E), the
marginal distribution of a is a mixture of two negative binomials, and we
maximise its likelihood over all pairs.

The posterior of each lambda is again a mixture of two gammas, from which:
- EBGM = exp(E[log lambda | a]), the shrunk reporting ratio
- EB05 / EB95 = 5th / 95th percentiles of the posterior
Signal: EB05 >= 2 (the usual FDA threshold).

Only pairs with a >= 1 are stored in drug_event_counts, so the likelihood is
truncated at zero (as in the openEBGM R package with zeroes = FALSE).
"""

from dataclasses import dataclass

import numpy as np
from scipy import optimize, special

# Starting values suggested by DuMouchel (1999).
DEFAULT_START = (0.2, 0.1, 2.0, 4.0, 1 / 3)


@dataclass
class Prior:
    alpha1: float
    beta1: float
    alpha2: float
    beta2: float
    p: float  # weight of the first component

    def as_tuple(self):
        return self.alpha1, self.beta1, self.alpha2, self.beta2, self.p


def _log_negbin(a, e, alpha, beta):
    """log P(a | E) when lambda ~ Gamma(alpha, rate = beta) and a ~ Poisson(lambda E)."""
    return (
        special.gammaln(alpha + a) - special.gammaln(alpha) - special.gammaln(a + 1)
        + alpha * np.log(beta / (beta + e)) + a * np.log(e / (beta + e))
    )


def _log_p_zero(e, alpha, beta):
    return alpha * np.log(beta / (beta + e))


def negative_log_likelihood(params, a, e, truncated=True):
    """Minus the log-likelihood of the mixture prior (params on the real line)."""
    alpha1, beta1, alpha2, beta2 = np.exp(params[:4])
    p = special.expit(params[4])
    log_f1 = _log_negbin(a, e, alpha1, beta1)
    log_f2 = _log_negbin(a, e, alpha2, beta2)
    log_mix = np.logaddexp(np.log(p) + log_f1, np.log1p(-p) + log_f2)
    if truncated:
        p0 = p * np.exp(_log_p_zero(e, alpha1, beta1)) + (1 - p) * np.exp(
            _log_p_zero(e, alpha2, beta2)
        )
        log_mix = log_mix - np.log1p(-np.minimum(p0, 1 - 1e-12))
    return -np.sum(log_mix)


def fit_prior(a, e, start=DEFAULT_START, truncated=True):
    """Estimate the 5 prior parameters by maximum likelihood."""
    a, e = np.asarray(a, dtype=float), np.asarray(e, dtype=float)
    x0 = np.r_[np.log(start[:4]), special.logit(start[4])]
    result = optimize.minimize(
        negative_log_likelihood, x0, args=(a, e, truncated), method="L-BFGS-B",
        bounds=[(-10, 10)] * 4 + [(-10, 10)],
    )
    if not result.success:
        raise RuntimeError(f"Prior fit did not converge: {result.message}")
    alpha1, beta1, alpha2, beta2 = np.exp(result.x[:4])
    return Prior(alpha1, beta1, alpha2, beta2, special.expit(result.x[4]))


def _posterior_weight(a, e, prior):
    """Probability that the pair belongs to the first prior component, given a."""
    log_w1 = np.log(prior.p) + _log_negbin(a, e, prior.alpha1, prior.beta1)
    log_w2 = np.log1p(-prior.p) + _log_negbin(a, e, prior.alpha2, prior.beta2)
    return special.expit(log_w1 - log_w2)


def _posterior_cdf(x, a, e, q, prior):
    """P(lambda <= x | a) for the two-gamma posterior."""
    cdf1 = special.gammainc(prior.alpha1 + a, (prior.beta1 + e) * x)
    cdf2 = special.gammainc(prior.alpha2 + a, (prior.beta2 + e) * x)
    return q * cdf1 + (1 - q) * cdf2


def posterior_quantile(prob, a, e, prior, iterations=60):
    """Quantile of the posterior, by bisection on log(lambda) (vectorised)."""
    a, e = np.asarray(a, dtype=float), np.asarray(e, dtype=float)
    q = _posterior_weight(a, e, prior)
    low = np.full(a.shape, -30.0)
    high = np.full(a.shape, 30.0)
    for _ in range(iterations):
        mid = (low + high) / 2
        below = _posterior_cdf(np.exp(mid), a, e, q, prior) < prob
        low = np.where(below, mid, low)
        high = np.where(below, high, mid)
    return np.exp((low + high) / 2)


def ebgm(a, e, prior):
    """EBGM, EB05 and EB95 for every pair, plus the EB05 >= 2 signal flag."""
    a, e = np.asarray(a, dtype=float), np.asarray(e, dtype=float)
    q = _posterior_weight(a, e, prior)
    mean_log = q * (special.digamma(prior.alpha1 + a) - np.log(prior.beta1 + e)) + (1 - q) * (
        special.digamma(prior.alpha2 + a) - np.log(prior.beta2 + e)
    )
    eb05 = posterior_quantile(0.05, a, e, prior)
    eb95 = posterior_quantile(0.95, a, e, prior)
    return {"ebgm": np.exp(mean_log), "eb05": eb05, "eb95": eb95, "signal": eb05 >= 2}
