"""Run the time-to-detection benchmark and store its results.

Steps:
1. Dated positives: drug-event pairs whose reaction was added to the label by
   a safety-related labelling change (SrLC) between 2016 and the end of the
   data window, and that are observed in FAERS (clinical terms only).
   Terms that are the drug's own indication (they appear in boxed warnings
   such as "patients with asthma") and the generic term "death" are dropped.
2. Controls: a random sample of label-based negatives (reactions not on the
   current label) of the same drugs, to measure false alarms over time.
3. Replay the database quarter by quarter and record the first quarter in
   which each method flags each pair (faers.temporal).

Usage (after make scores and make reference):

    python -m faers.benchmark
"""

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd

from faers.load import DB_PATH
from faers.reference import clean_text, fetch_label, load_label_reference, mentions
from faers.srlc import dated_pairs, load_changes
from faers.temporal import build_quarterly_counts, first_signal_dates

FIRST_QUARTER_END = "2014-09-30"
LAST_QUARTER_END = "2026-06-30"
OUTPUT = Path("reports/tables/first_signals.csv")


def is_indication(row):
    """True if the term is mentioned in the indications of the drug's current label."""
    label = fetch_label(row.drug)
    if label is None:
        return False
    return mentions(clean_text(" ".join(label.get("indications_and_usage", []))), row.pt)


def build_targets(con, n_negatives=20_000, seed=0):
    """Dated positives (from SrLC) plus a sample of label-based negatives."""
    observed = con.execute("SELECT drug, pt FROM drug_event_counts").df()
    positives = dated_pairs(load_changes(), observed)
    positives = positives[(positives.label_date >= "2016-01-01") & (positives.pt != "death")]
    positives = positives[~positives.apply(is_indication, axis=1)].copy()
    positives["group"] = "label change"

    reference = load_label_reference(con)
    negatives = reference[
        (reference.status == "negative") & reference.drug.isin(positives.drug)
    ][["drug", "pt"]]
    negatives = negatives.sample(min(n_negatives, len(negatives)), random_state=seed)
    negatives["group"] = "not on label"
    return pd.concat([positives, negatives], ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description="Time-to-detection benchmark.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    con = duckdb.connect(str(args.db))
    start = time.time()
    build_quarterly_counts(con)
    targets = build_targets(con)
    print(f"Targets: {targets.group.value_counts().to_dict()} ({time.time() - start:.0f} s)")

    quarter_ends = pd.date_range(FIRST_QUARTER_END, LAST_QUARTER_END, freq="QE")
    first = first_signal_dates(con, targets, quarter_ends)
    result = targets.merge(first, on=["drug", "pt"], how="left")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"Saved {len(result):,} pairs to {args.output} ({time.time() - start:.0f} s)")
    con.close()


if __name__ == "__main__":
    main()
