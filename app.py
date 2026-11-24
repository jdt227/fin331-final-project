"""
Streamlit dashboard — Estimate-Driven Crowding: Does Analyst Consensus
Drive Institutional Herding and Worsen Earnings Outcomes?

Run with:  streamlit run app.py
"""
import streamlit as st
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

ROOT    = Path(__file__).parent
INPUTS  = ROOT / "inputs"
OUTPUTS = ROOT / "outputs"
FIGURES = OUTPUTS / "figures"

st.set_page_config(
    page_title="Estimate-Driven Crowding",
    page_icon="📊",
    layout="wide",
)


# ── Load data (cached) ─────────────────────────────────────────────────────────

@st.cache_data
def load_data():
    ds_path    = INPUTS / "final_dataset.parquet"
    qret_path  = OUTPUTS / "quintile_returns.csv"
    gret_path  = OUTPUTS / "growth_quintile_returns.csv"
    tt_path    = OUTPUTS / "two_by_two.csv"
    reg_path   = OUTPUTS / "regression_results.csv"
    chan_path   = OUTPUTS / "channel_test.csv"
    fi_path    = OUTPUTS / "feature_importance.csv"
    ml_path    = OUTPUTS / "ml_summary.csv"

    df    = pd.read_parquet(ds_path)       if ds_path.exists()   else None
    qret  = pd.read_csv(qret_path)         if qret_path.exists() else None
    gret  = pd.read_csv(gret_path)         if gret_path.exists() else None
    tt    = pd.read_csv(tt_path)           if tt_path.exists()   else None
    reg   = pd.read_csv(reg_path)          if reg_path.exists()  else None
    chan  = pd.read_csv(chan_path)          if chan_path.exists()  else None
    fi    = pd.read_csv(fi_path)           if fi_path.exists()   else None
    ml    = pd.read_csv(ml_path)           if ml_path.exists()   else None
    return df, qret, gret, tt, reg, chan, fi, ml


df, qret, gret, tt, reg, chan, fi, ml_summary = load_data()

# ── Header ─────────────────────────────────────────────────────────────────────

st.title("📊 Estimate-Driven Crowding")
st.caption(
    "FIN 331 Final Project · Syracuse University · "
    "Do large analyst EPS revisions herd institutions into the same stocks, "
    "and do crowded positions fare worse at earnings?"
)
st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs(
    ["🏠 Introduction", "🔬 Methodology", "📈 Results", "🔍 Explore"]
)

# ══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Introduction
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Research Hypothesis")
    st.markdown(
        """
When analysts revise EPS estimates sharply upward, many institutions react
by buying the same stocks — creating **crowded trades**. We test whether:

1. **Channel effect** — positive estimate revisions predict higher crowding rank
2. **Fragility** — entering earnings in a crowded stock produces lower CAR[-1,+1]
3. **Drift** — crowded stocks underperform further over CAR[+2,+60]
4. **Interaction** — crowding amplifies EPS surprise (beat doesn't save a crowded stock)
"""
    )

    if df is not None:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Stock-Quarter Obs", f"{len(df):,}")
        c2.metric("Unique Tickers", f"{df['ticker'].nunique():,}")
        n_q = df["fpedats"].nunique() if "fpedats" in df.columns else "—"
        c3.metric("Fiscal Quarters", str(n_q))
        car_cov = df["car_event"].notna().mean() if "car_event" in df.columns else 0
        c4.metric("CAR Coverage", f"{car_cov:.0%}")

        crowding_cov = df["crowding_rank"].notna().mean() if "crowding_rank" in df.columns else 0
        st.success(
            f"**Full sample run** — real WRDS IBES consensus and EDGAR 13F crowding data. "
            f"Crowding coverage: {crowding_cov:.0%} of rows."
        )
    else:
        st.warning("Run the pipeline first:\n\n```bash\npython run_all.py\n```")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Methodology
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Data Sources")
    st.markdown(
        """
| Source | Variable | Frequency |
|--------|----------|-----------|
| WRDS IBES statsum_epsus | EPS consensus, std dev, n analysts | Quarterly snapshot |
| SEC Form 13F (EDGAR) | n_filers, chg_filers | Calendar quarter |
| yfinance (adjusted close) | Daily returns for CAR | Daily |
| Wikipedia S&P 500 table | Constituent filter | Current membership |
"""
    )

    st.subheader("Key Variables")
    st.markdown(
        r"""
**eps_revision** = (consensus_t − consensus_tm1) / |consensus_tm1|
   • Same fiscal period, two snapshot dates (winsorized at 1/99th pct)

**revision_streak** = consecutive quarters with eps_revision > 1%

**dispersion** = analyst std dev / |eps_consensus| (coefficient of variation)

**crowding_rank** = percentile of n_filers within S&P 500 that calendar quarter

**Look-ahead rule (1-quarter lag)**
   Crowding rank from calendar quarter Q predicts CAR at earnings in Q+1
   (13F filings become public ≈45 days after Q end; Q+1 earnings follow)

**car_event** = Σ(stock_ret − SPY_ret) over [-1, +1] trading days around announcement
**car_drift** = Σ(stock_ret − SPY_ret) over [+2, +60] trading days after announcement
"""
    )

    st.subheader("Fiscal → Calendar Quarter Alignment")
    st.markdown(
        """
Not all companies end fiscal quarters on Mar/Jun/Sep/Dec.
We map each fiscal period end date to the most recent calendar quarter end
on or before it, then join 13F crowding data on that calendar quarter.
Rows where fiscal = calendar quarter end are flagged `fiscal_qtr_match = True`.
"""
    )

# ══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Results
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    if qret is None:
        st.warning("Run `python code/06_analysis.py` to generate results.")
    else:
        # Finding 1 — Fragility sort
        st.subheader("Finding 1: Fragility Sort — CAR by Crowding Quintile")
        col_a, col_b = st.columns(2)

        qcar_fig = FIGURES / "quintile_car.png"
        if qcar_fig.exists():
            col_a.image(str(qcar_fig), caption="CAR[-1,+1] and CAR[+2,+60] by crowding quintile")

        with col_b:
            display = qret.copy()
            display["mean_car_event"] = display["mean_car_event"].map("{:.3%}".format)
            display["mean_car_drift"] = display["mean_car_drift"].map("{:.3%}".format) \
                if "mean_car_drift" in display.columns else "—"
            st.dataframe(display, use_container_width=True)

        st.divider()

        # Finding 2 — 2×2 heatmap
        st.subheader("Finding 2: Crowding × Revision → CAR at Earnings")
        col_c, col_d = st.columns(2)

        heatmap_fig = FIGURES / "two_by_two_heatmap.png"
        if heatmap_fig.exists():
            col_c.image(str(heatmap_fig))

        if tt is not None:
            with col_d:
                st.markdown(
                    """
**Interpretation:**
High crowding + High revision = worst quadrant (consensus already rich;
no one left to buy).
Low crowding + High revision = best outcome (genuine underappreciated upgrade).
"""
                )
                st.dataframe(tt, use_container_width=True)

        st.divider()

        # Finding 3 — Expected growth → crowding channel
        st.subheader("Finding 3: Does Expected EPS Jump Predict Crowding?")
        col_g1, col_g2 = st.columns(2)
        eg_fig = FIGURES / "expected_growth_vs_crowding.png"
        if eg_fig.exists():
            col_g1.image(str(eg_fig), caption="Expected EPS growth vs crowding rank")
        scat_fig = FIGURES / "revision_vs_crowding.png"
        if scat_fig.exists():
            col_g2.image(str(scat_fig), caption="EPS revision vs crowding rank")

        if chan is not None:
            st.caption(
                "Channel test (OLS): does expected growth predict institutional crowding? "
                "p-values shown below."
            )
            st.dataframe(chan.style.format({"coef": "{:.4f}", "se": "{:.4f}", "pval": "{:.3f}"}),
                         use_container_width=True)

        st.divider()

        # Finding 4a — Growth quintile sort (new)
        st.subheader("Finding 4: CAR by Expected EPS Growth Quintile")
        col_ga, col_gb = st.columns(2)
        gq_fig = FIGURES / "growth_quintile_car.png"
        if gq_fig.exists():
            col_ga.image(str(gq_fig))
        if gret is not None:
            with col_gb:
                display_g = gret.copy()
                display_g["mean_car_event"] = display_g["mean_car_event"].map("{:.3%}".format)
                display_g["mean_car_drift"] = display_g["mean_car_drift"].map("{:.3%}".format) \
                    if "mean_car_drift" in display_g.columns else "—"
                st.dataframe(display_g, use_container_width=True)
                st.caption(
                    "Q1 = stocks where analysts expect the smallest EPS jump vs last quarter. "
                    "Q5 = largest expected jump. No clear penalty for high expectations alone — "
                    "crowding is the driver."
                )

        st.divider()

        # Finding 5 — Drift chart
        st.subheader("Finding 5: Post-Earnings Drift")
        col_e, col_f = st.columns(2)
        drift_fig = FIGURES / "drift_by_quintile.png"
        if drift_fig.exists():
            col_e.image(str(drift_fig))

        ts_fig = FIGURES / "crowding_ts.png"
        if ts_fig.exists():
            col_f.image(str(ts_fig))

        st.divider()

        # Regression table
        st.subheader("OLS Regression: car_event ~ crowding_rank + eps_surprise + controls")
        if reg is not None:
            st.dataframe(
                reg.style.format({"coef": "{:.4f}", "se": "{:.4f}", "pval": "{:.3f}"}),
                use_container_width=True,
            )
            st.caption(
                "HC3 robust standard errors. Quarter fixed effects included but not shown."
            )

        st.divider()

        # ML model
        st.subheader("ML Model: Random Forest Feature Importances")
        col_ml1, col_ml2 = st.columns([1, 1])

        fi_fig = FIGURES / "feature_importance.png"
        if fi_fig.exists():
            col_ml1.image(str(fi_fig))

        with col_ml2:
            if ml_summary is not None:
                row = ml_summary.iloc[0]
                st.metric("OOS R²", f"{row['oos_r2']:.4f}")
                st.metric("OOS MAE", f"{row['oos_mae']:.4f}")
                st.metric("Directional Accuracy", f"{row['directional_accuracy']:.1%}")
                st.caption(
                    f"Random Forest Regressor, 5-fold walk-forward CV. "
                    f"Target: CAR[−1,+1]. "
                    f"N = {int(row['n_obs'])} obs, {int(row['n_tickers'])} tickers. "
                    f"eps_surprise dominates; crowding_rank is second most important feature."
                )
            if fi is not None:
                st.dataframe(fi.style.format({"importance": "{:.4f}"}),
                             use_container_width=True)

        actual_pred_fig = FIGURES / "ml_actual_vs_pred.png"
        if actual_pred_fig.exists():
            st.image(str(actual_pred_fig), width=400,
                     caption="OOS actual vs predicted CAR[-1,+1]")

# ══════════════════════════════════════════════════════════════════════════════
# Tab 4 — Interactive Exploration
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Stock Explorer")
    if df is None:
        st.warning("Run the pipeline first to explore individual stocks.")
    else:
        tickers_avail = sorted(df["ticker"].unique())
        sel_ticker = st.selectbox("Select ticker", tickers_avail, index=0)

        stock_df = df[df["ticker"] == sel_ticker].copy()
        stock_df = stock_df.sort_values("fpedats")

        if stock_df.empty:
            st.info(f"No data for {sel_ticker}.")
        else:
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Quarters",        f"{len(stock_df)}")
            m2.metric("Avg Crowding Rank",
                       f"{stock_df['crowding_rank'].mean():.2f}"
                       if "crowding_rank" in stock_df else "—")
            m3.metric("Avg EPS Revision",
                       f"{stock_df['eps_revision'].mean():.1%}"
                       if "eps_revision" in stock_df else "—")
            m4.metric("Avg CAR[-1,+1]",
                       f"{stock_df['car_event'].mean():.2%}"
                       if "car_event" in stock_df else "—")

            # Three-panel chart
            fig, axes = plt.subplots(3, 1, figsize=(9, 8), sharex=True)
            dates = stock_df["fpedats"]

            axes[0].plot(dates, stock_df.get("crowding_rank", pd.Series(dtype=float)),
                         marker="o", color="#3498db")
            axes[0].set_ylabel("Crowding Rank")
            axes[0].set_title(f"{sel_ticker} — Crowding, Revision, and Earnings CAR")
            axes[0].set_ylim(0, 1)

            axes[1].bar(dates, stock_df.get("eps_revision", pd.Series(dtype=float)),
                        color=["#2ecc71" if v >= 0 else "#e74c3c"
                               for v in stock_df.get("eps_revision",
                                                     pd.Series(dtype=float)).fillna(0)])
            axes[1].axhline(0, color="black", linewidth=0.6)
            axes[1].set_ylabel("EPS Revision")

            car_col = stock_df.get("car_event", pd.Series(dtype=float))
            axes[2].bar(dates, car_col * 100,
                        color=["#2ecc71" if v >= 0 else "#e74c3c"
                               for v in car_col.fillna(0)])
            axes[2].axhline(0, color="black", linewidth=0.6)
            axes[2].set_ylabel("CAR[-1,+1] (%)")
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
            plt.close()

            # Detail table
            show_cols = [c for c in
                         ["fpedats", "eps_revision", "revision_streak",
                          "dispersion", "crowding_rank", "eps_surprise",
                          "car_event", "car_drift"]
                         if c in stock_df.columns]
            fmt_map = {c: "{:.3f}" for c in show_cols if c != "fpedats"
                       and c != "revision_streak"}
            st.dataframe(
                stock_df[show_cols].style.format(fmt_map),
                use_container_width=True,
            )

        # Bottom: most crowded in latest quarter
        st.divider()
        st.subheader("Most Crowded Stocks — Latest Fiscal Quarter")
        latest = df["fpedats"].max()
        top10  = (
            df[df["fpedats"] == latest]
            .nlargest(10, "crowding_rank")
            [["ticker", "crowding_rank", "eps_revision", "car_event"]]
        )
        st.dataframe(
            top10.style.format({
                "crowding_rank": "{:.2f}",
                "eps_revision":  "{:.2%}",
                "car_event":     "{:.2%}",
            }),
            use_container_width=True,
        )
