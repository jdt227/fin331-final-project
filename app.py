"""
Crowded Trades dashboard.   Run:  streamlit run app.py

Reads only files in outputs/ (made by run_all.py), so every number shown traces to a file.
If outputs/ is empty, it shows a clearly labelled TOY dataset so the layout can be built
before the real data exists.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

OUT = Path(__file__).resolve().parent / "outputs"
TAB = OUT / "tables"
st.set_page_config(page_title="Crowded Trades", layout="wide")


@st.cache_data
def load():
    f = OUT / "final_dataset.parquet"
    if f.exists():
        return pd.read_parquet(f), False
    # ---- toy data, same columns the real pipeline produces
    rng = np.random.default_rng(0)
    qs = [str(q) for q in pd.period_range("2022Q1", "2024Q4", freq="Q")]
    tick = ["AAPL", "MSFT", "NVDA", "AMZN", "JPM", "XOM", "TSLA", "META", "UNH", "KO"]
    d = pd.DataFrame([(q, t) for q in qs for t in tick], columns=["quarter", "ticker"])
    d["n_holders"] = rng.integers(1500, 6000, len(d))
    d["dbreadth"] = rng.normal(0, 1, len(d))
    d["net_buyer_frac"] = rng.uniform(-0.3, 0.3, len(d))
    d["pct_chg_holders"] = rng.normal(0, 0.03, len(d))
    d["exret_fwd"] = rng.normal(0, 0.08, len(d))
    d["crowd_score"] = (d.groupby("quarter")["n_holders"].rank(pct=True) * 50
                        + d.groupby("quarter")["dbreadth"].rank(pct=True) * 50).round(1)
    d["formation_date"] = pd.to_datetime([pd.Period(q).end_time.normalize()
                                          + pd.Timedelta(days=46) for q in d["quarter"]])
    return d, True


def table(name):
    p = TAB / name
    return pd.read_csv(p) if p.exists() else None


d, toy = load()
if toy:
    st.warning("TOY DATA — run `python run_all.py` to build outputs/. Nothing below is a result.")

st.title("Crowded Trades")
st.caption("Do stocks that many institutions piled into last quarter do worse afterward?")

tab_intro, tab_method, tab_results, tab_explore = st.tabs(
    ["Overview", "Methodology", "Results", "Crowding explorer"])

# ------------------------------------------------------------------ Overview
with tab_intro:
    head = json.loads((TAB / "headline_numbers.json").read_text()) \
        if (TAB / "headline_numbers.json").exists() else None
    c1, c2, c3, c4 = st.columns(4)
    if head:
        c1.metric("Sample", head["sample_quarters"])
        c2.metric("Stock-quarters", f"{head['n_stock_quarters']:,}")
        c3.metric("Most − least crowded, next quarter",
                  f"{head['primary_q5_minus_q1_per_quarter'] * 100:.2f}%",
                  help="Average quarterly return of the most-crowded quintile minus the "
                       "least-crowded quintile, in excess of SPY. Source: "
                       "outputs/tables/headline_numbers.json")
        c4.metric("t-statistic", f"{head['primary_t_stat']:.2f}")
    st.markdown("""
**The question.** Every quarter, institutional managers with over $100M must disclose
their U.S. stock holdings on SEC Form 13F. When many managers buy the same stock at once,
the trade is "crowded." If they all need to sell at once, prices can fall hard.
We test whether crowding predicts **next-quarter returns**, using only information that
was public at the time.

**Who would pay for this.** A risk manager at a fund who wants to know whether the
positions they share with many other funds carry hidden downside.
""")

# ------------------------------------------------------------------ Methodology
with tab_method:
    st.markdown("""
| Step | What happens | Code |
|---|---|---|
| 1 | Download SEC Form 13F structured data sets | `src/01_download_13f.py` |
| 2 | Keep original 13F-HR filings made by the 45-day deadline; build manager × stock holdings | `src/02_parse_13f.py` |
| 3 | Count holders; map CUSIP → ticker with OpenFIGI; pick the 500 largest common stocks each quarter | `src/03_universe_and_cusip_map.py` |
| 4 | Download adjusted prices (Yahoo Finance) | `src/04_download_prices.py` |
| 5 | Crowding measures + returns from the first trading day after the deadline | `src/05_build_dataset.py` |
| 6 | Quintile sorts, Fama-MacBeth and pooled regressions, costs | `src/06_analysis.py` |
| 7 | Independent hand checks | `src/07_hand_checks.py` |

**Timing.** Holdings at the end of quarter *q* are public only by quarter end + 45 days.
Positions are formed at the close of the first trading day after that deadline and held
until the next formation date.

**Primary crowding measure (pre-registered):** change in ownership breadth
(Chen, Hong & Stein 2002) — among managers who filed in both quarters, the change in the
share of them holding the stock, in percentage points.
""")
    fc = table("filing_filter_counts.csv")
    if fc is not None:
        st.subheader("How many filings each rule removed")
        st.dataframe(fc, hide_index=True)

# ------------------------------------------------------------------ Results
with tab_results:
    qr = table("quintile_returns.csv")
    if qr is None:
        st.info("Run the pipeline to see results.")
    else:
        sig = st.selectbox("Crowding measure", qr["signal"].unique())
        show = qr[qr["signal"] == sig].set_index("quintile")["mean_exret_fwd"] * 100
        st.subheader("Average next-quarter return minus SPY (%), by crowding quintile")
        st.bar_chart(show)
        st.caption("Quintile 5 = most crowded. Source: outputs/tables/quintile_returns.csv")
        c1, c2 = st.columns(2)
        c1.subheader("Long-short summary")
        c1.dataframe(table("long_short_summary.csv"), hide_index=True)
        c2.subheader("Does timing matter? (look-ahead check)")
        c2.dataframe(table("lookahead_comparison.csv"), hide_index=True)
        st.subheader("Fama-MacBeth regressions (variables standardized within quarter)")
        st.dataframe(table("fama_macbeth.csv").query("signal == @sig"), hide_index=True)
        st.subheader("After trading costs")
        st.dataframe(table("magnitude.csv"), hide_index=True)
        for img in ["quintile_returns.png", "cumulative_long_short.png"]:
            if (OUT / "figures" / img).exists():
                st.image(str(OUT / "figures" / img))

# ------------------------------------------------------------------ Explorer
with tab_explore:
    tickers = sorted(d["ticker"].unique())
    t = st.selectbox("Ticker", tickers, index=tickers.index("AAPL") if "AAPL" in tickers else 0)
    g = d[d["ticker"] == t].sort_values("quarter").set_index("quarter")
    c1, c2 = st.columns(2)
    c1.subheader("Crowding score (0-100)")
    c1.line_chart(g["crowd_score"])
    c2.subheader("Number of 13F holders")
    c2.line_chart(g["n_holders"])
    st.caption("Crowding score = average of the stock's within-quarter percentile rank in "
               "number of holders and in change in breadth. Descriptive only.")
    cols = [c for c in ["n_holders", "dbreadth", "net_buyer_frac", "crowd_score",
                        "formation_date", "exret_fwd"] if c in g.columns]
    st.dataframe(g[cols])
    q = st.selectbox("Most crowded stocks in quarter", sorted(d["quarter"].unique())[::-1])
    st.dataframe(d[d["quarter"] == q].nlargest(20, "crowd_score")[["ticker"] + cols],
                 hide_index=True)
