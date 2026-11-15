"""Score every drug-event pair with every disproportionality method.

Usage (from the repository root, after `python -m faers.transform`):

    python -m faers.scores

Creates two tables in the warehouse:
- signal_scores: one row per drug-event pair with the counts and, for each
  method, its estimate, lower bound and signal flag
- ebgm_prior: the 5 parameters of the MGPS prior fitted on the data

counts_as_of() rebuilds the 2x2 table using only the reports the FDA had
received by a given date (init_fda_dt). It is the building block for the
time-to-detection analysis: running the methods quarter by quarter shows
when each one first flags a known adverse reaction.
"""

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd

from faers.ebgm import ebgm as ebgm_scores
from faers.ebgm import fit_prior
from faers.load import DB_PATH
from faers.methods import bcpnn, expected, prr, ror

COUNTS_AS_OF_SQL = """
WITH rde AS (
    SELECT primaryid, drug, pt FROM report_drug_event WHERE init_fda_dt <= ?
),
total AS (SELECT COUNT(DISTINCT primaryid) AS n_total FROM rde),
per_drug AS (SELECT drug, COUNT(DISTINCT primaryid) AS n_drug FROM rde GROUP BY drug),
per_event AS (SELECT pt, COUNT(DISTINCT primaryid) AS n_event FROM rde GROUP BY pt),
pairs AS (SELECT drug, pt, COUNT(DISTINCT primaryid) AS a FROM rde GROUP BY drug, pt)
SELECT
    p.drug, p.pt, p.a,
    d.n_drug - p.a                          AS b,
    e.n_event - p.a                         AS c,
    t.n_total - d.n_drug - e.n_event + p.a  AS d
FROM pairs AS p
JOIN per_drug AS d USING (drug)
JOIN per_event AS e USING (pt)
CROSS JOIN total AS t
"""


def load_counts(con):
    """The full-window 2x2 table (drug_event_counts) as a DataFrame."""
    return con.execute("SELECT drug, pt, a, b, c, d FROM drug_event_counts").df()


def counts_as_of(con, cutoff):
    """2x2 table using only cases first received by the FDA on or before cutoff."""
    return con.execute(COUNTS_AS_OF_SQL, [pd.Timestamp(cutoff).date()]).df()


def score_pairs(counts, prior=None):
    """Add the columns of every method to a DataFrame with a, b, c, d.

    If no EBGM prior is given, it is fitted on these same counts.
    Returns (scored DataFrame, prior).
    """
    a, b, c, d = (counts[col].to_numpy(dtype=float) for col in "abcd")
    out = counts.copy()
    out["expected"] = expected(a, b, c, d)
    if prior is None:
        prior = fit_prior(a, out["expected"].to_numpy())
    results = {
        "prr": prr(a, b, c, d),
        "ror": ror(a, b, c, d),
        "bcpnn": bcpnn(a, b, c, d),
        "ebgm": ebgm_scores(a, out["expected"].to_numpy(), prior),
    }
    for method, columns in results.items():
        for name, values in columns.items():
            column = f"{method}_signal" if name == "signal" else name
            out[column] = values
    return out, prior


def main():
    parser = argparse.ArgumentParser(description="Score all drug-event pairs.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()

    con = duckdb.connect(str(args.db))
    start = time.time()
    counts = load_counts(con)
    print(f"{len(counts):,} pairs loaded ({time.time() - start:.0f} s)", flush=True)
    scored, prior = score_pairs(counts)
    print(f"Scores computed ({time.time() - start:.0f} s). EBGM prior: {prior}", flush=True)

    con.register("scored_df", scored)
    con.execute("CREATE OR REPLACE TABLE signal_scores AS SELECT * FROM scored_df")
    con.execute(
        "CREATE OR REPLACE TABLE ebgm_prior AS SELECT ? AS alpha1, ? AS beta1, "
        "? AS alpha2, ? AS beta2, ? AS p",
        list(prior.as_tuple()),
    )
    summary = con.execute("""
        SELECT COUNT(*) AS pairs,
               SUM(prr_signal::INT) AS prr, SUM(ror_signal::INT) AS ror,
               SUM(bcpnn_signal::INT) AS bcpnn, SUM(ebgm_signal::INT) AS ebgm
        FROM signal_scores
    """).df()
    print("\nSignals per method:")
    print(summary.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
