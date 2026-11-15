"""Export a compact copy of the results for the Streamlit app (app/).

The full warehouse is ~10 GB; the app only needs:
- signals.parquet: every drug-event pair with at least MIN_REPORTS reports and
  its four scores
- timeline.parquet: reports per quarter for the pairs of the time-to-detection
  benchmark, plus drug, event and total counts per quarter, so the app can
  replay any method over time
- label_changes.parquet: the dated reference (label change date per pair)

Usage (after make scores and python -m faers.benchmark):

    python -m faers.export
"""

import argparse
from pathlib import Path

import duckdb
import pandas as pd

from faers.load import DB_PATH

APP_DATA = Path("app/data")
MIN_REPORTS = 5
FIRST_SIGNALS = Path("reports/tables/first_signals.csv")


def export(con, out_dir=APP_DATA, min_reports=MIN_REPORTS):
    out_dir.mkdir(parents=True, exist_ok=True)
    con.execute(f"""
        COPY (
            SELECT drug, pt, a::INTEGER AS a, (a + b)::INTEGER AS n_drug,
                   ROUND(expected, 2)::FLOAT AS expected, ROUND(prr, 2)::FLOAT AS prr,
                   ROUND(ror_lower, 2)::FLOAT AS ror_lower, ROUND(ic025, 2)::FLOAT AS ic025,
                   ROUND(ebgm, 2)::FLOAT AS ebgm, ROUND(eb05, 2)::FLOAT AS eb05,
                   prr_signal, ror_signal, bcpnn_signal, ebgm_signal
            FROM signal_scores WHERE a >= {int(min_reports)}
        ) TO '{out_dir / "signals.parquet"}' (FORMAT parquet, COMPRESSION zstd)
    """)

    targets = pd.read_csv(FIRST_SIGNALS)
    positives = targets[targets.group == "label change"][["drug", "pt", "label_date", "section"]]
    positives.to_parquet(out_dir / "label_changes.parquet", index=False)

    con.register("timeline_pairs", positives[["drug", "pt"]])
    con.execute(f"""
        COPY (SELECT p.* FROM pair_quarter AS p JOIN timeline_pairs USING (drug, pt))
        TO '{out_dir / "pair_quarter.parquet"}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.execute(f"""
        COPY (SELECT d.* FROM drug_quarter AS d
              WHERE drug IN (SELECT DISTINCT drug FROM timeline_pairs))
        TO '{out_dir / "drug_quarter.parquet"}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.execute(f"""
        COPY (SELECT e.* FROM event_quarter AS e
              WHERE pt IN (SELECT DISTINCT pt FROM timeline_pairs))
        TO '{out_dir / "event_quarter.parquet"}' (FORMAT parquet, COMPRESSION zstd)
    """)
    con.execute(f"""
        COPY total_quarter TO '{out_dir / "total_quarter.parquet"}' (FORMAT parquet)
    """)
    con.execute(f"""
        COPY ebgm_prior TO '{out_dir / "ebgm_prior.parquet"}' (FORMAT parquet)
    """)


def main():
    parser = argparse.ArgumentParser(description="Export app data.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args()
    con = duckdb.connect(str(args.db), read_only=True)
    export(con)
    con.close()
    for path in sorted(APP_DATA.glob("*.parquet")):
        print(f"{path.name:<24}{path.stat().st_size / 1e6:8.1f} MB")


if __name__ == "__main__":
    main()
