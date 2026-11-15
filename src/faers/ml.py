"""Machine-learning models that combine the disproportionality scores with
features of the reports themselves.

Idea: a reporting ratio alone ignores *who* reported and *how serious* the
cases were. A model can learn, from known adverse reactions, how much weight
to give to each piece of evidence.

Features per drug-event pair (all from FAERS):
- counts and scores: a, E, PRR, ROR lower bound, IC025, EB05 (log scale)
- case mix: share of serious, fatal and hospitalised cases; share of reports
  from health professionals, consumers and lawyers; share from the US;
  share of women; median age
- dynamics: number of years with reports, share of reports in the last two years

Models: L2-penalised logistic regression and histogram gradient boosting.
Evaluation uses GroupKFold by drug, so the model is always tested on drugs
it has never seen (no leakage between pairs of the same drug).
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

FEATURES_SQL = """
WITH serious AS (
    SELECT primaryid,
           MAX(CASE WHEN outc_cod IN ('DE', 'LT', 'HO', 'DS', 'CA', 'RI') THEN 1 ELSE 0 END)
               AS serious,
           MAX(CASE WHEN outc_cod = 'DE' THEN 1 ELSE 0 END) AS death,
           MAX(CASE WHEN outc_cod = 'HO' THEN 1 ELSE 0 END) AS hospital
    FROM outc_clean GROUP BY primaryid
)
SELECT
    r.drug, r.pt,
    AVG(COALESCE(s.serious, 0))                                         AS share_serious,
    AVG(COALESCE(s.death, 0))                                           AS share_death,
    AVG(COALESCE(s.hospital, 0))                                        AS share_hospital,
    AVG(CASE WHEN dm.occp_cod IN ('MD', 'PH', 'HP', 'OT') THEN 1 ELSE 0 END) AS share_hcp,
    AVG(CASE WHEN dm.occp_cod = 'CN' THEN 1 ELSE 0 END)                AS share_consumer,
    AVG(CASE WHEN dm.occp_cod = 'LW' THEN 1 ELSE 0 END)                AS share_lawyer,
    AVG(CASE WHEN dm.reporter_country = 'US' THEN 1 ELSE 0 END)        AS share_us,
    AVG(CASE WHEN dm.sex = 'F' THEN 1 ELSE 0 END)                      AS share_female,
    MEDIAN(CASE WHEN dm.age_cod = 'YR' AND dm.age BETWEEN 0 AND 110 THEN dm.age END) AS median_age,
    COUNT(DISTINCT YEAR(r.init_fda_dt))                                AS years_reported,
    AVG(CASE WHEN r.init_fda_dt >= DATE '2024-07-01' THEN 1 ELSE 0 END) AS share_recent
FROM report_drug_event AS r
JOIN target_pairs USING (drug, pt)
JOIN demo_dedup AS dm USING (primaryid)
LEFT JOIN serious AS s USING (primaryid)
GROUP BY r.drug, r.pt
"""

LOG_FEATURES = ["a", "expected", "prr", "ror_lower", "eb05", "n_drug", "n_event"]
PLAIN_FEATURES = [
    "ic025", "share_serious", "share_death", "share_hospital", "share_hcp", "share_consumer",
    "share_lawyer", "share_us", "share_female", "median_age", "years_reported", "share_recent",
]


def pair_features(con, pairs):
    """Case-mix and dynamics features for the given (drug, pt) pairs."""
    con.register("target_pairs", pairs[["drug", "pt"]].drop_duplicates())
    return con.execute(FEATURES_SQL).df()


def design_matrix(df):
    """Model inputs: log of the skewed counts and ratios, the rest as they are."""
    X = pd.DataFrame(index=df.index)
    for column in LOG_FEATURES:
        # Ratios can be infinite (an empty cell in the 2x2 table): cap them.
        values = df[column].replace([np.inf, -np.inf], np.nan).clip(lower=1e-6, upper=1e6)
        X[f"log_{column}"] = np.log(values.fillna(1e6))
    for column in PLAIN_FEATURES:
        X[column] = df[column].replace([np.inf, -np.inf], np.nan)
    return X.fillna(X.median())


def models():
    return {
        "Logistic regression": make_pipeline(
            StandardScaler(), LogisticRegression(C=1.0, max_iter=2000, class_weight="balanced")
        ),
        "Gradient boosting": HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=31, l2_regularization=1.0,
            class_weight="balanced", random_state=0,
        ),
    }


def out_of_fold_scores(X, y, groups, n_splits=5):
    """Predicted probability for every pair, from models that never saw its drug."""
    scores = {name: np.zeros(len(y)) for name in models()}
    for train, test in GroupKFold(n_splits=n_splits).split(X, y, groups):
        for name, model in models().items():
            model.fit(X.iloc[train], y.iloc[train])
            scores[name][test] = model.predict_proba(X.iloc[test])[:, 1]
    return pd.DataFrame(scores, index=X.index)


def logistic_coefficients(X, y):
    """Standardised coefficients of the logistic model fitted on all pairs."""
    model = models()["Logistic regression"].fit(X, y)
    coefs = model[-1].coef_[0]
    return pd.Series(coefs, index=X.columns).sort_values(key=np.abs, ascending=False)
