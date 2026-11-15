"""Build a reference set of known and not-known adverse reactions from drug labels.

For the most reported primary suspect drugs, the current FDA label is taken
from openFDA (api.fda.gov) and every drug-event pair observed in FAERS gets a
status:

- positive: the reaction is mentioned in a safety section of the label
  (boxed warning, contraindications, warnings and precautions, adverse
  reactions)
- negative: the reaction is not mentioned anywhere in the label
- excluded: mentioned only outside the safety sections (for example as the
  indication or in clinical studies), so its status is ambiguous

Matching is done on text: MedDRA preferred terms use British spelling
(oedema, haemorrhage) and US labels American spelling, so terms are converted
first. It is a deliberately simple, transparent reference with known
limitations: a reaction described with other words on the label counts as a
negative, and a mention does not always mean a causal reaction.

To keep the repository small, ref/label_reference.csv stores only the
positive and excluded pairs, and ref/label_drugs.csv the label used for each
drug: every other observed pair of those drugs is a negative
(see load_label_reference).

Usage (from the repository root, needs internet access to api.fda.gov):

    python -m faers.reference              # top 300 drugs
    python -m faers.reference --drugs 50   # quicker test
"""

import argparse
import json
import re
import time
from pathlib import Path

import duckdb
import pandas as pd
import requests

from faers.load import DB_PATH

API = "https://api.fda.gov/drug/label.json"
ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "labels"
OUTPUT = ROOT / "ref" / "label_reference.csv"
DRUGS_OUTPUT = ROOT / "ref" / "label_drugs.csv"

SAFETY_SECTIONS = [
    "boxed_warning", "contraindications", "warnings_and_cautions", "warnings",
    "precautions", "adverse_reactions", "adverse_reactions_table",
]

# British (MedDRA) -> American (US labels) spelling, applied to preferred terms.
SPELLING = [
    (r"oedema", "edema"), (r"haem", "hem"), (r"aemia", "emia"), (r"oesoph", "esoph"),
    (r"oea\b", "ea"), (r"foet", "fet"), (r"paed", "ped"), (r"tumour", "tumor"),
    (r"ischaem", "ischem"), (r"leukaem", "leukem"), (r"anaesth", "anesth"),
    (r"oestr", "estr"), (r"colour", "color"), (r"behaviour", "behavior"),
    (r"orrhoea", "orrhea"), (r"\boe", "e"), (r"aesthe", "esthe"), (r"faec", "fec"),
    (r"caec", "cec"), (r"coeli", "celi"), (r"glycaem", "glycem"), (r"kalaem", "kalem"),
    (r"natraem", "natrem"), (r"calcaem", "calcem"), (r"lipidaem", "lipidem"),
    (r"sulph", "sulf"), (r"diarrhoea", "diarrhea"), (r"apnoea", "apnea"),
    (r"dyspnoea", "dyspnea"),
]


def to_us_spelling(term):
    """'Oedema peripheral' -> 'edema peripheral'; 'haemorrhage' -> 'hemorrhage'."""
    term = term.lower()
    for pattern, replacement in SPELLING:
        term = re.sub(pattern, replacement, term)
    return term


def clean_text(text):
    """Lower case, punctuation as spaces, single spaces, padded for whole-word search."""
    return " " + " ".join(re.sub(r"[^a-z0-9]+", " ", text.lower()).split()) + " "


def mentions(text, term):
    """True if the (cleaned) term appears as whole words in the cleaned text."""
    return clean_text(to_us_spelling(term)) in text


def select_drugs(con, n):
    """The n single-ingredient primary suspect drugs with the most reports."""
    return [row[0] for row in con.execute("""
        SELECT drug FROM (SELECT DISTINCT drug, n_drug FROM drug_event_counts)
        WHERE drug NOT LIKE '%\\%' ORDER BY n_drug DESC LIMIT ?
    """, [n]).fetchall()]


def _label_size(label):
    return sum(len(" ".join(label.get(section, []))) for section in SAFETY_SECTIONS)


def fetch_label(drug, cache_dir=CACHE_DIR):
    """The most complete current prescription label for a single-ingredient drug.

    Results are cached in data/labels/ so the API is called once per drug.
    Returns a dict (the openFDA label) or None if no suitable label exists.
    """
    cache = cache_dir / f"{re.sub(r'[^A-Z0-9]+', '_', drug)}.json"
    if cache.exists():
        return json.loads(cache.read_text()) or None
    params = {"search": f'openfda.generic_name:"{drug}"', "limit": 25}
    for attempt in range(4):
        response = requests.get(API, params=params, timeout=60)
        if response.status_code != 429:
            break
        time.sleep(10 * (attempt + 1))  # rate limited: wait and retry
    labels = response.json().get("results", []) if response.status_code == 200 else []
    candidates = [
        label for label in labels
        if label.get("openfda", {}).get("product_type") == ["HUMAN PRESCRIPTION DRUG"]
        and len(label["openfda"].get("generic_name", [])) == 1
        and " AND " not in label["openfda"]["generic_name"][0]
        and _label_size(label) > 0
    ]
    best = max(candidates, key=_label_size) if candidates else None
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(best or {}))
    return best


def label_texts(label):
    """(safety text, full text), both cleaned for whole-word search."""
    safety = " ".join(" ".join(label.get(section, [])) for section in SAFETY_SECTIONS)
    everything = " ".join(
        " ".join(value) for key, value in label.items()
        if isinstance(value, list) and value and isinstance(value[0], str) and key != "openfda"
    )
    return clean_text(safety), clean_text(everything)


def classify_pairs(drug, pts, label):
    """Status of every (drug, pt) pair given the drug's label."""
    safety, everything = label_texts(label)
    rows = []
    for pt in pts:
        if mentions(safety, pt):
            status = "positive"
        elif mentions(everything, pt):
            status = "excluded"
        else:
            status = "negative"
        rows.append((drug, pt, status))
    return rows


def build_reference(con, n_drugs, cache_dir=CACHE_DIR):
    drugs = select_drugs(con, n_drugs)
    rows, meta = [], []
    for i, drug in enumerate(drugs, 1):
        label = fetch_label(drug, cache_dir)
        if label is None:
            continue
        pts = [r[0] for r in con.execute(
            "SELECT pt FROM drug_event_counts WHERE drug = ?", [drug]).fetchall()]
        rows += classify_pairs(drug, pts, label)
        meta.append((drug, label.get("set_id"), label.get("effective_time")))
        if i % 25 == 0:
            print(f"{i}/{len(drugs)} drugs", flush=True)
    reference = pd.DataFrame(rows, columns=["drug", "pt", "status"])
    labels = pd.DataFrame(meta, columns=["drug", "set_id", "label_date"])
    return reference.merge(labels, on="drug")


def load_label_reference(con, reference=OUTPUT, drugs=DRUGS_OUTPUT):
    """Status of every observed pair of the reference drugs (negatives filled in)."""
    con.register("label_pairs", pd.read_csv(reference))
    con.register("label_drugs", pd.read_csv(drugs))
    return con.execute("""
        SELECT c.drug, c.pt, COALESCE(r.status, 'negative') AS status
        FROM drug_event_counts AS c
        JOIN label_drugs USING (drug)
        LEFT JOIN label_pairs AS r USING (drug, pt)
    """).df()


def main():
    parser = argparse.ArgumentParser(description="Build the label-based reference set.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--drugs", type=int, default=300)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    con = duckdb.connect(str(args.db), read_only=True)
    reference = build_reference(con, args.drugs)
    con.close()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    reference[reference.status != "negative"][["drug", "pt", "status"]].to_csv(
        args.output, index=False)
    reference[["drug", "set_id", "label_date"]].drop_duplicates().to_csv(DRUGS_OUTPUT, index=False)
    print(f"\n{reference.drug.nunique()} drugs with a label, {len(reference):,} pairs")
    print(reference.status.value_counts().to_string())


if __name__ == "__main__":
    main()
