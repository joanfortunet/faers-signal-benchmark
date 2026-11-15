"""Time to detection: when does each method first flag a drug-event pair?

The database is replayed quarter by quarter: at the end of every quarter
only the cases the FDA had received by then (init_fda_dt) are counted, and
every method is applied to the 2x2 tables of that moment.

Because each case has one receipt date, counts per quarter simply add up:
a(pair, up to quarter t) = sum of a(pair, quarter q) for q <= t, and the
same for the drug totals, event totals and N. So the per-quarter counts are
computed once (quarterly_counts) and cumulated, instead of recounting 40 M
rows 48 times.

The MGPS prior is refitted at every quarter end on a random sample of all
pairs observed by then, so EBGM also only uses information available at
that moment.
"""

import numpy as np
import pandas as pd

from faers.ebgm import ebgm, fit_prior
from faers.methods import bcpnn, expected, prr, ror

METHODS = ["prr", "ror", "bcpnn", "ebgm"]

QUARTERLY_SQL = """
CREATE OR REPLACE TABLE pair_quarter AS
SELECT drug, pt, LAST_DAY(DATE_TRUNC('quarter', init_fda_dt) + INTERVAL 2 MONTH) AS quarter_end,
       COUNT(DISTINCT primaryid) AS n
FROM report_drug_event GROUP BY ALL;

CREATE OR REPLACE TABLE drug_quarter AS
SELECT drug, LAST_DAY(DATE_TRUNC('quarter', init_fda_dt) + INTERVAL 2 MONTH) AS quarter_end,
       COUNT(DISTINCT primaryid) AS n
FROM report_drug_event GROUP BY ALL;

CREATE OR REPLACE TABLE event_quarter AS
SELECT pt, LAST_DAY(DATE_TRUNC('quarter', init_fda_dt) + INTERVAL 2 MONTH) AS quarter_end,
       COUNT(DISTINCT primaryid) AS n
FROM report_drug_event GROUP BY ALL;

CREATE OR REPLACE TABLE total_quarter AS
SELECT LAST_DAY(DATE_TRUNC('quarter', init_fda_dt) + INTERVAL 2 MONTH) AS quarter_end,
       COUNT(DISTINCT primaryid) AS n
FROM report_drug_event GROUP BY ALL;
"""


def build_quarterly_counts(con):
    """Per-quarter counts of pairs, drugs, events and reports (run once)."""
    con.execute(QUARTERLY_SQL)


def counts_until(con, cutoff, pairs=None, sample=None, seed=0):
    """Cumulative 2x2 tables at a quarter end.

    pairs: DataFrame with drug, pt columns to restrict to (target pairs).
    sample: number of random pairs to return instead (used to fit the prior).
    """
    if pairs is not None:
        con.register("target_pairs", pairs[["drug", "pt"]])
        pair_filter = "JOIN target_pairs USING (drug, pt)"
    else:
        pair_filter = ""
    limit = f"USING SAMPLE {int(sample)} ROWS (reservoir, {seed})" if sample else ""
    return con.execute(f"""
        WITH a AS (
            SELECT drug, pt, SUM(n) AS a FROM pair_quarter {pair_filter}
            WHERE quarter_end <= ? GROUP BY drug, pt
        ),
        a_sample AS (SELECT * FROM a {limit}),
        nd AS (SELECT drug, SUM(n) AS n_drug FROM drug_quarter
               WHERE quarter_end <= ? GROUP BY drug),
        ne AS (SELECT pt, SUM(n) AS n_event FROM event_quarter
               WHERE quarter_end <= ? GROUP BY pt),
        nt AS (SELECT SUM(n) AS n_total FROM total_quarter WHERE quarter_end <= ?)
        SELECT drug, pt, a,
               n_drug - a AS b, n_event - a AS c, n_total - n_drug - n_event + a AS d
        FROM a_sample JOIN nd USING (drug) JOIN ne USING (pt) CROSS JOIN nt
    """, [cutoff] * 4).df()


def signals_at(counts, prior):
    """Boolean signal flag of every method for a table of counts."""
    a, b, c, d = (counts[col].to_numpy(dtype=float) for col in "abcd")
    e = expected(a, b, c, d)
    return pd.DataFrame({
        "prr": prr(a, b, c, d)["signal"],
        "ror": ror(a, b, c, d)["signal"],
        "bcpnn": bcpnn(a, b, c, d)["signal"],
        "ebgm": ebgm(a, e, prior)["signal"],
    }, index=counts.index)


def first_signal_dates(con, pairs, quarter_ends, prior_sample=200_000, prior=None,
                       verbose=True):
    """For every target pair, the first quarter end at which each method flags it.

    The EBGM prior is refitted at each quarter end unless a fixed prior is given.
    Returns a DataFrame: drug, pt, first_<method> (NaT if never flagged).
    """
    result = pairs[["drug", "pt"]].drop_duplicates().reset_index(drop=True)
    for method in METHODS:
        result[f"first_{method}"] = pd.NaT
    for i, cutoff in enumerate(quarter_ends):
        quarter_prior = prior
        if quarter_prior is None:
            sample = counts_until(con, cutoff, sample=prior_sample, seed=i)
            sa, sb, sc, sd = (sample[col].to_numpy(dtype=float) for col in "abcd")
            quarter_prior = fit_prior(sa, expected(sa, sb, sc, sd))
        counts = counts_until(con, cutoff, pairs=result)
        flags = signals_at(counts, quarter_prior)
        flagged = counts[["drug", "pt"]].join(flags)
        merged = result[["drug", "pt"]].merge(flagged, on=["drug", "pt"], how="left")
        for method in METHODS:
            column = f"first_{method}"
            flagged_now = merged[method].fillna(False).to_numpy(dtype=bool)
            new = flagged_now & result[column].isna().to_numpy()
            result.loc[new, column] = pd.Timestamp(cutoff)
        if verbose:
            day = pd.Timestamp(cutoff).date()
            print(f"{day}: {len(counts):,} target pairs observed", flush=True)
    return result


def lead_times(first_dates, label_dates):
    """Months between the first signal and the label change (positive = earlier).

    label_dates: DataFrame with drug, pt, label_date.
    """
    out = first_dates.merge(label_dates, on=["drug", "pt"])
    for method in METHODS:
        delta = out["label_date"] - out[f"first_{method}"]
        out[f"lead_{method}"] = delta.dt.days / 30.44
    return out


def summarise_lead_times(leads):
    """Per method: share detected before the label change and median lead time."""
    rows = []
    for method in METHODS:
        lead = leads[f"lead_{method}"]
        rows.append({
            "method": method,
            "detected_ever": lead.notna().mean(),
            "detected_before_label": (lead > 0).mean(),
            "median_lead_months": lead[lead > 0].median() if (lead > 0).any() else np.nan,
        })
    return pd.DataFrame(rows)


def replay_pair(con, drug, pt, quarter_ends, prior):
    """Counts and lower-bound scores of one pair at every quarter end (for case studies)."""
    pair = pd.DataFrame({"drug": [drug], "pt": [pt]})
    rows = []
    for cutoff in quarter_ends:
        counts = counts_until(con, cutoff, pairs=pair)
        if counts.empty:
            continue
        a, b, c, d = (counts[col].to_numpy(dtype=float) for col in "abcd")
        e = expected(a, b, c, d)
        rows.append({
            "quarter_end": pd.Timestamp(cutoff), "a": int(a[0]),
            "prr_lower": prr(a, b, c, d)["prr_lower"][0],
            "ror_lower": ror(a, b, c, d)["ror_lower"][0],
            "ic025": bcpnn(a, b, c, d)["ic025"][0],
            "eb05": ebgm(a, e, prior)["eb05"][0],
        })
    return pd.DataFrame(rows)
