"""Metrics to compare signal detection methods against a reference set.

Each method is used as a ranking score (higher = more suspicious) and
compared with the reference labels (1 = known adverse reaction, 0 = not on
the label):

- ROC AUC: probability that a random positive is ranked above a random negative
- Average precision (AP): area under the precision-recall curve, more
  informative than AUC when positives are rare
- Precision@k: share of known reactions among the k highest-ranked pairs
- Sensitivity / specificity / PPV of each method's own signal threshold

Confidence intervals come from a bootstrap that resamples whole drugs,
because pairs of the same drug are not independent.
"""

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

# Score used to rank pairs for each method (the lower bound, as used in practice).
RANKING_SCORES = {
    "PRR": "prr_lower",
    "ROR": "ror_lower",
    "BCPNN": "ic025",
    "EBGM": "eb05",
}
BASELINES = {"Count (a)": "a", "Observed/expected": "ratio"}
SIGNAL_FLAGS = {"PRR": "prr_signal", "ROR": "ror_signal", "BCPNN": "bcpnn_signal",
                "EBGM": "ebgm_signal"}


def precision_at_k(y, score, k):
    order = np.argsort(-np.asarray(score), kind="stable")[:k]
    return float(np.asarray(y)[order].mean())


def ranking_metrics(y, score, ks=(100, 1000)):
    y, score = np.asarray(y), np.asarray(score, dtype=float)
    finite = score[np.isfinite(score)]
    low = finite.min() - 1 if finite.size else 0.0
    # Missing scores rank last; infinite ones are kept at the extremes.
    high = finite.max() + 1 if finite.size else 1.0
    score = np.nan_to_num(score, nan=low, neginf=low, posinf=high)
    out = {"auc": roc_auc_score(y, score), "ap": average_precision_score(y, score)}
    for k in ks:
        out[f"p@{k}"] = precision_at_k(y, score, k)
    return out


def compare_rankings(df, scores, label="label"):
    """One row per score column: AUC, AP, precision@k. df needs a 0/1 label."""
    rows = [{"method": name, **ranking_metrics(df[label], df[column])}
            for name, column in scores.items()]
    return pd.DataFrame(rows).set_index("method")


def threshold_metrics(df, flags=SIGNAL_FLAGS, label="label"):
    """Sensitivity, specificity and PPV of each method's signal threshold."""
    rows = []
    y = df[label].astype(bool)
    for name, column in flags.items():
        flagged = df[column].astype(bool)
        rows.append({
            "method": name,
            "signals": int(flagged.sum()),
            "sensitivity": (flagged & y).sum() / y.sum(),
            "specificity": (~flagged & ~y).sum() / (~y).sum(),
            "ppv": (flagged & y).sum() / max(flagged.sum(), 1),
        })
    return pd.DataFrame(rows).set_index("method")


def bootstrap_by_drug(df, scores, metric="auc", n_boot=200, label="label", seed=0):
    """Bootstrap (resampling drugs) mean and 95 % interval of a metric per score."""
    rng = np.random.default_rng(seed)
    groups = {drug: idx for drug, idx in df.groupby("drug").indices.items()}
    drugs = np.array(list(groups))
    results = {name: [] for name in scores}
    for _ in range(n_boot):
        chosen = rng.choice(drugs, size=len(drugs), replace=True)
        idx = np.concatenate([groups[d] for d in chosen])
        sample = df.iloc[idx]
        if sample[label].nunique() < 2:
            continue
        for name, column in scores.items():
            results[name].append(ranking_metrics(sample[label], sample[column], ks=())[metric])
    return pd.DataFrame({
        name: {"mean": np.mean(v), "low": np.percentile(v, 2.5), "high": np.percentile(v, 97.5)}
        for name, v in results.items()
    }).T
