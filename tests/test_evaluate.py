import numpy as np
import pandas as pd
import pytest

from faers.evaluate import (
    bootstrap_by_drug,
    compare_rankings,
    precision_at_k,
    ranking_metrics,
    threshold_metrics,
)
from faers.ml import design_matrix, out_of_fold_scores


def test_perfect_and_random_rankings():
    y = np.array([1, 1, 0, 0])
    assert ranking_metrics(y, [4, 3, 2, 1], ks=())["auc"] == 1
    assert ranking_metrics(y, [1, 2, 3, 4], ks=())["auc"] == 0
    assert precision_at_k(y, [4, 3, 2, 1], 2) == 1


def test_missing_scores_rank_last():
    y = np.array([1, 0])
    assert ranking_metrics(y, [1.0, np.nan], ks=())["auc"] == 1


def test_compare_and_threshold_tables():
    df = pd.DataFrame({
        "drug": ["A", "A", "B", "B"], "label": [1, 0, 1, 0],
        "good": [0.9, 0.1, 0.8, 0.2], "bad": [0.1, 0.9, 0.2, 0.8],
        "prr_signal": [True, False, True, True], "ror_signal": [True] * 4,
        "bcpnn_signal": [False] * 4, "ebgm_signal": [True, False, False, False],
    })
    table = compare_rankings(df, {"Good": "good", "Bad": "bad"}, )
    assert table.loc["Good", "auc"] == 1 and table.loc["Bad", "auc"] == 0
    thresholds = threshold_metrics(df)
    assert thresholds.loc["PRR", "sensitivity"] == 1
    assert thresholds.loc["PRR", "ppv"] == pytest.approx(2 / 3)
    assert thresholds.loc["EBGM", "specificity"] == 1


def test_bootstrap_by_drug_gives_an_interval():
    rng = np.random.default_rng(1)
    n = 400
    df = pd.DataFrame({"drug": rng.integers(0, 40, n).astype(str),
                       "label": rng.integers(0, 2, n)})
    df["score"] = df.label + rng.normal(0, 1, n)
    ci = bootstrap_by_drug(df, {"Score": "score"}, n_boot=50)
    assert ci.loc["Score", "low"] < ci.loc["Score", "mean"] < ci.loc["Score", "high"]


def test_models_learn_an_informative_feature():
    rng = np.random.default_rng(0)
    n = 600
    df = pd.DataFrame({
        "drug": rng.integers(0, 30, n), "label": rng.integers(0, 2, n),
        "a": rng.integers(1, 100, n), "expected": rng.uniform(0.5, 50, n),
        "prr": rng.uniform(0.5, 5, n), "ror_lower": rng.uniform(0.2, 4, n),
        "n_drug": rng.integers(100, 1000, n), "n_event": rng.integers(100, 1000, n),
        "ic025": rng.normal(0, 1, n), "share_death": rng.uniform(0, 1, n),
        "share_hospital": rng.uniform(0, 1, n), "share_hcp": rng.uniform(0, 1, n),
        "share_consumer": rng.uniform(0, 1, n), "share_lawyer": rng.uniform(0, 1, n),
        "share_us": rng.uniform(0, 1, n), "share_female": rng.uniform(0, 1, n),
        "median_age": rng.uniform(20, 80, n), "years_reported": rng.integers(1, 12, n),
        "share_recent": rng.uniform(0, 1, n),
    })
    # The known reactions have a higher EB05 and more serious cases.
    df["eb05"] = np.exp(df.label * 1.5 + rng.normal(0, 1, n))
    df["share_serious"] = (0.3 + 0.3 * df.label + rng.normal(0, 0.1, n)).clip(0, 1)
    oof = out_of_fold_scores(design_matrix(df), df.label, df.drug)
    for model in oof:
        assert ranking_metrics(df.label, oof[model], ks=())["auc"] > 0.8
