"""FAERS signal explorer.

Run locally (from the repository root):

    streamlit run app/app.py

Data come from app/data/ (created by `python -m faers.export`).
"""

import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from faers.ebgm import Prior, ebgm  # noqa: E402
from faers.methods import bcpnn, prr, ror  # noqa: E402

DATA = ROOT / "app" / "data"
METHODS = {
    "EBGM (EB05 ≥ 2)": ("eb05", "ebgm_signal"),
    "BCPNN (IC025 > 0)": ("ic025", "bcpnn_signal"),
    "PRR (Evans)": ("prr", "prr_signal"),
    "ROR (lower bound > 1)": ("ror_lower", "ror_signal"),
}
COLORS = {"PRR": "#2a78d6", "ROR": "#eb6834", "BCPNN": "#1baf7a", "EBGM": "#eda100"}

st.set_page_config(page_title="FAERS signal explorer", layout="wide")


@st.cache_data
def load():
    signals = pd.read_parquet(DATA / "signals.parquet")
    changes = pd.read_parquet(DATA / "label_changes.parquet")
    changes["label_date"] = pd.to_datetime(changes["label_date"])
    timeline = {
        name: pd.read_parquet(DATA / f"{name}.parquet")
        for name in ["pair_quarter", "drug_quarter", "event_quarter", "total_quarter"]
    }
    for frame in timeline.values():
        frame["quarter_end"] = pd.to_datetime(frame["quarter_end"])
    prior = Prior(**pd.read_parquet(DATA / "ebgm_prior.parquet").iloc[0].to_dict())
    return signals, changes, timeline, prior


def replay(drug, pt, timeline, prior):
    """Scores of one pair at every quarter end, using only reports received by then."""
    def cumulative(df, **keys):
        sub = df
        for column, value in keys.items():
            sub = sub[sub[column] == value]
        return sub.groupby("quarter_end")["n"].sum()

    quarters = timeline["total_quarter"].sort_values("quarter_end")["quarter_end"]
    frame = pd.DataFrame(index=pd.Index(quarters, name="quarter_end"))
    frame["a"] = cumulative(timeline["pair_quarter"], drug=drug, pt=pt)
    frame["n_drug"] = cumulative(timeline["drug_quarter"], drug=drug)
    frame["n_event"] = cumulative(timeline["event_quarter"], pt=pt)
    frame["n_total"] = timeline["total_quarter"].set_index("quarter_end")["n"]
    frame = frame.fillna(0).cumsum()
    frame = frame[(frame.a > 0) & (frame.index >= pd.Timestamp("2014-09-30"))]
    a, nd, ne, n = (frame[c].to_numpy(dtype=float) for c in ["a", "n_drug", "n_event", "n_total"])
    b, c = nd - a, ne - a
    d = n - nd - ne + a
    frame["PRR"] = prr(a, b, c, d)["prr_lower"]
    frame["ROR"] = ror(a, b, c, d)["ror_lower"]
    frame["BCPNN"] = bcpnn(a, b, c, d)["ic025"]
    frame["EBGM"] = ebgm(a, nd * ne / n, prior)["eb05"]
    return frame.reset_index()


signals, changes, timeline, prior = load()

st.title("FAERS signal explorer")
st.caption(
    "Disproportionality signals for every drug–event pair with at least 5 reports in the "
    "FDA Adverse Event Reporting System, 2014 Q3 – 2026 Q2 (16.2 M deduplicated cases). "
    "Signal ≠ causality: FAERS is a spontaneous reporting system."
)

tab_drug, tab_time, tab_about = st.tabs(["Signals by drug", "Signal over time", "About"])

with tab_drug:
    drugs = signals.groupby("drug")["n_drug"].first().sort_values(ascending=False)
    col1, col2, col3 = st.columns([2, 2, 1])
    drug = col1.selectbox("Drug (primary suspect)", drugs.index, index=0)
    method = col2.selectbox("Rank by", list(METHODS))
    only_signals = col3.checkbox("Only signals", value=True)
    score, flag = METHODS[method]
    table = signals[signals.drug == drug].sort_values(score, ascending=False)
    if only_signals:
        table = table[table[flag]]
    st.metric("Reports with this drug as primary suspect", f"{int(drugs[drug]):,}")
    st.write(f"{len(table):,} reactions shown, ranked by {method}.")
    shown = table[["pt", "a", "expected", "prr", "ror_lower", "ic025", "ebgm", "eb05",
                   "prr_signal", "ror_signal", "bcpnn_signal", "ebgm_signal"]].head(200)
    st.dataframe(
        shown.rename(columns={"pt": "reaction", "a": "reports", "expected": "expected (E)",
                              "ror_lower": "ROR lower", "ic025": "IC025", "eb05": "EB05"}),
        hide_index=True, width="stretch",
    )

with tab_time:
    st.write(
        "Reactions added to the US label by a safety-related labelling change "
        "(FDA SrLC, 2016–2026). The chart replays the database quarter by quarter: "
        "each line is the lower bound of a method's estimate with the data available "
        "at that time, and the dashed line marks the label change."
    )
    drugs_with_changes = sorted(changes.drug.unique())
    col1, col2 = st.columns(2)
    default_drug = (
        drugs_with_changes.index("MONTELUKAST") if "MONTELUKAST" in drugs_with_changes else 0
    )
    drug_t = col1.selectbox("Drug", drugs_with_changes, index=default_drug)
    events = changes[changes.drug == drug_t].sort_values("pt")
    pt_t = col2.selectbox("Reaction added to the label", events.pt)
    label_date = events.set_index("pt").loc[pt_t, "label_date"]
    frame = replay(drug_t, pt_t, timeline, prior)
    thresholds = {"PRR": 1, "ROR": 1, "BCPNN": 0, "EBGM": 2}
    long = frame.melt(id_vars=["quarter_end", "a"], value_vars=list(COLORS),
                      var_name="method", value_name="lower bound")
    for name, threshold in thresholds.items():
        first = frame[frame[name] > threshold]["quarter_end"].min()
        st.write(f"**{name}** first above its threshold: "
                 f"{'never' if pd.isna(first) else pd.Timestamp(first).date()}")
    chart = alt.Chart(long).mark_line(strokeWidth=2).encode(
        x=alt.X("quarter_end:T", title="Quarter"),
        y=alt.Y("lower bound:Q", title="Lower bound of the estimate"),
        color=alt.Color("method:N", scale=alt.Scale(domain=list(COLORS),
                                                     range=list(COLORS.values()))),
        tooltip=["quarter_end:T", "method:N", alt.Tooltip("lower bound:Q", format=".2f"),
                 alt.Tooltip("a:Q", title="reports")],
    )
    rule = alt.Chart(pd.DataFrame({"date": [label_date]})).mark_rule(
        strokeDash=[6, 4], color="#52514e").encode(x="date:T")
    st.altair_chart(chart + rule, width="stretch")
    st.caption(f"Label change: {pd.Timestamp(label_date).date()}. "
               f"Reports by the end of the window: {int(frame.a.max()) if len(frame) else 0}.")

with tab_about:
    st.markdown(
        """
**Methods** (all implemented from scratch in `src/faers/`):

| Method | Signal when |
|---|---|
| PRR — proportional reporting ratio | a ≥ 3, PRR ≥ 2, χ² ≥ 4 (Evans) |
| ROR — reporting odds ratio | a ≥ 3 and lower 95 % bound > 1 |
| BCPNN — information component | IC025 > 0 |
| MGPS — empirical Bayes geometric mean | EB05 ≥ 2 |

**Data:** FDA FAERS quarterly files, cases deduplicated (latest version of each case),
primary suspect drug only, non-clinical terms (medication errors, off-label use,
lack of efficacy, product issues) excluded.

**Limitations:** spontaneous reports cannot give incidence or prove causality, and
are affected by notoriety bias, stimulated reporting and confounding by indication.

Source code: [github.com/joanfortunet/faers-signal-benchmark](https://github.com/joanfortunet/faers-signal-benchmark)
        """
    )
