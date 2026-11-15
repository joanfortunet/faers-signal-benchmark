"""Dated reference set from the FDA Drug Safety-related Labeling Changes (SrLC).

The SrLC database (https://www.accessdata.fda.gov/scripts/cder/safetylabelingchanges/)
lists every safety-related labelling change approved since 2016, with its
date and the text that was added (underlined, or whole newly added sections).

ref/srlc_label_changes.csv.gz holds the additions to the boxed warning,
contraindications, warnings and precautions and adverse reactions sections
for the benchmark drugs (one row per drug, application, date and section).
It was collected with a normal browser session, because the site does not
allow scripted downloads.

A drug-event pair gets a label date when its preferred term is mentioned in
the text added by a labelling change: the earliest such date is the moment
the FDA officially acknowledged the reaction. Those pairs are the positives
of the time-to-detection analysis.
"""

from pathlib import Path

import pandas as pd

from faers.reference import clean_text, mentions

ROOT = Path(__file__).resolve().parents[2]
CHANGES = ROOT / "ref" / "srlc_label_changes.csv.gz"

# Names collected before the fumarate-ester fix in faers.normalize.
RENAMES = {"DIMETHYL": "DIMETHYL FUMARATE", "DIROXIMEL": "DIROXIMEL FUMARATE"}


def load_changes(path=CHANGES):
    changes = pd.read_csv(path, parse_dates=["date"], date_format="%m/%d/%Y")
    changes["drug"] = changes["drug"].replace(RENAMES)
    return changes.drop_duplicates()


def dated_pairs(changes, observed_pairs):
    """Earliest labelling change mentioning each observed (drug, pt) pair.

    observed_pairs: DataFrame with drug, pt (the clinical pairs seen in FAERS).
    Returns drug, pt, label_date, section.
    """
    rows = []
    for drug, drug_changes in changes.sort_values("date").groupby("drug"):
        pts = observed_pairs.loc[observed_pairs.drug == drug, "pt"].unique()
        if len(pts) == 0:
            continue
        found = {}
        for change in drug_changes.itertuples():
            text = clean_text(change.added_text)
            for pt in pts:
                if pt not in found and mentions(text, pt):
                    found[pt] = (change.date, change.section)
        rows += [(drug, pt, date, section) for pt, (date, section) in found.items()]
    return pd.DataFrame(rows, columns=["drug", "pt", "label_date", "section"])
