"""
Step 8: Analysis — four empirical tests of the estimate-crowding hypothesis.

1. Channel test  — does eps_revision predict crowding_rank?
2. Fragility sort — car_event and car_drift by crowding quintile
3. 2×2 table     — high/low crowding × high/low eps_revision → mean car_event
4. Regression    — car_event ~ crowding_rank * eps_surprise + revision_streak + dispersion

Outputs (all in outputs/):
  quintile_returns.csv           — mean CAR by crowding quintile
  two_by_two.csv                 — 2×2 crowding × revision table
  regression_results.csv         — OLS coefficient table
  figures/quintile_car.png
  figures/two_by_two_heatmap.png
  figures/revision_vs_crowding.png
  figures/crowding_ts.png
  figures/drift_by_quintile.png
"""
import sys
import warnings
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import statsmodels.formula.api as smf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import INPUTS, OUTPUTS, FIGURES

sns.set_theme(style="whitegrid", palette="muted")
warnings.filterwarnings("ignore", category=FutureWarning)

DS = INPUTS / "final_dataset.parquet"


# ── Helpers ────────────────────────────────────────────────────────────────────

def quintile_label(s: pd.Series, q: int = 5) -> pd.Series:
    """Rank series into q groups (1=lowest, q=highest); handles ties/duplicates."""
    return pd.qcut(s.rank(method="first"), q=q, labels=False, duplicates="drop") + 1


def winsorize(s: pd.Series, pct: float = 0.01) -> pd.Series:
    lo, hi = s.quantile(pct), s.quantile(1 - pct)
    return s.clip(lo, hi)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    OUTPUTS.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(DS)
    df["fpedats"] = pd.to_datetime(df["fpedats"])
    df["calendar_qtr_end"] = pd.to_datetime(df["calendar_qtr_end"])

    # Winsorize continuous outcomes to reduce outlier influence
    for col in ["car_event", "car_drift", "eps_revision", "dispersion"]:
        if col in df.columns:
            df[col] = winsorize(df[col].astype(float))

    n_tickers = df["ticker"].nunique()
    n_rows    = len(df)
    print(f"Analysis dataset: {n_rows:,} stock-quarter obs, {n_tickers:,} tickers")

    # ── Quintile assignment (within quarter) ───────────────────────────────────
    df["crowding_q"] = df.groupby("fpedats")["crowding_rank"].transform(
        lambda x: quintile_label(x, q=min(5, x.notna().sum()))
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Analysis 1: Channel test — does revision predict crowding?
    # ─────────────────────────────────────────────────────────────────────────
    ch_df = df.dropna(subset=["crowding_rank", "eps_revision"])
    ch_model = smf.ols(
        "crowding_rank ~ eps_revision + revision_streak + dispersion",
        data=ch_df,
    ).fit(cov_type="HC3")
    print("\n--- Channel test: eps_revision → crowding_rank ---")
    tbl = ch_model.summary2().tables[1]
    cols = [c for c in ["Coef.", "Std.Err.", "t", "P>|t|"] if c in tbl.columns]
    print(tbl[cols].to_string())

    # ─────────────────────────────────────────────────────────────────────────
    # Analysis 2: Fragility sort — car by crowding quintile
    # ─────────────────────────────────────────────────────────────────────────
    sort_df = df.dropna(subset=["crowding_q", "car_event"])
    qret = (
        sort_df.groupby("crowding_q")
        .agg(
            mean_car_event=("car_event", "mean"),
            mean_car_drift=("car_drift",  "mean"),
            n_obs         =("car_event", "count"),
        )
        .reset_index()
        .rename(columns={"crowding_q": "crowding_q"})
    )
    qret.to_csv(OUTPUTS / "quintile_returns.csv", index=False)
    print("\n--- Fragility sort: CAR by crowding quintile ---")
    print(qret.to_string(index=False))

    # ─────────────────────────────────────────────────────────────────────────
    # Analysis 3: 2×2 table — crowding × revision → car_event
    # ─────────────────────────────────────────────────────────────────────────
    tt_df = df.dropna(subset=["crowding_rank", "eps_revision", "car_event"]).copy()
    tt_df["crowding_hi"] = (tt_df["crowding_rank"] >= tt_df["crowding_rank"].median()).astype(int)
    tt_df["revision_hi"] = (tt_df["eps_revision"]  >= tt_df["eps_revision"].median()).astype(int)

    two_by_two = (
        tt_df.groupby(["crowding_hi", "revision_hi"])
        .agg(mean_car_event=("car_event", "mean"), n_obs=("car_event", "count"))
        .reset_index()
    )
    two_by_two.to_csv(OUTPUTS / "two_by_two.csv", index=False)
    print("\n--- 2×2 table: crowding × revision ---")
    print(two_by_two.to_string(index=False))

    # ─────────────────────────────────────────────────────────────────────────
    # Analysis 4: OLS regression — car_event ~ crowding × surprise + controls
    # ─────────────────────────────────────────────────────────────────────────
    reg_df = df.dropna(subset=["crowding_rank", "eps_surprise", "car_event",
                                "revision_streak", "dispersion"]).copy()
    reg_df["qtr_fe"] = reg_df["fpedats"].dt.to_period("Q").astype(str)

    m1 = smf.ols(
        "car_event ~ crowding_rank + eps_surprise + revision_streak + dispersion + C(qtr_fe)",
        data=reg_df,
    ).fit(cov_type="HC3")

    m2 = smf.ols(
        "car_event ~ crowding_rank * eps_surprise + revision_streak + dispersion + C(qtr_fe)",
        data=reg_df,
    ).fit(cov_type="HC3")

    def extract_coefs(result, model_name):
        keep = ["crowding_rank", "eps_surprise", "revision_streak",
                "dispersion", "crowding_rank:eps_surprise"]
        rows = []
        for term in keep:
            if term in result.params.index:
                rows.append({
                    "model": model_name,
                    "term":  term,
                    "coef":  result.params[term],
                    "se":    result.bse[term],
                    "pval":  result.pvalues[term],
                })
        return rows

    reg_rows = extract_coefs(m1, "main") + extract_coefs(m2, "interaction")
    reg_out  = pd.DataFrame(reg_rows)
    reg_out.to_csv(OUTPUTS / "regression_results.csv", index=False)
    print("\n--- Regression results ---")
    print(reg_out.to_string(index=False))

    # ─────────────────────────────────────────────────────────────────────────
    # Figures
    # ─────────────────────────────────────────────────────────────────────────

    # Figure 1: Quintile CAR (event and drift)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    for ax, col, title in [
        (axes[0], "mean_car_event", "CAR[-1,+1] by Crowding Quintile"),
        (axes[1], "mean_car_drift", "CAR[+2,+60] by Crowding Quintile"),
    ]:
        vals   = qret[col] * 100
        colors = ["#2ecc71" if v > 0 else "#e74c3c" for v in vals]
        bars   = ax.bar(qret["crowding_q"].astype(str), vals,
                        color=colors, edgecolor="white", linewidth=0.8)
        ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
        ax.set_xlabel("Quintile (1 = least crowded, 5 = most crowded)")
        ax.set_ylabel("Avg CAR (%)")
        ax.set_title(title)
        ax.bar_label(bars, fmt="%.2f%%", padding=3, fontsize=9)
    fig.suptitle("Crowded Trades: Earnings Returns by Crowding Quintile", fontsize=13)
    plt.tight_layout()
    fig.savefig(FIGURES / "quintile_car.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure 2: 2×2 heatmap
    pivot = two_by_two.pivot(index="crowding_hi", columns="revision_hi",
                             values="mean_car_event") * 100
    pivot.index   = ["Low Crowding", "High Crowding"]
    pivot.columns = ["Low Revision", "High Revision"]
    fig, ax = plt.subplots(figsize=(6, 4))
    sns.heatmap(pivot, annot=True, fmt=".2f", cmap="RdYlGn",
                center=0, ax=ax, linewidths=0.5)
    ax.set_title("Mean CAR[-1,+1] (%) by Crowding and Estimate Revision")
    plt.tight_layout()
    fig.savefig(FIGURES / "two_by_two_heatmap.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure 3: Scatter — eps_revision vs crowding_rank
    scat_df = df.dropna(subset=["eps_revision", "crowding_rank"])
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.scatter(scat_df["eps_revision"], scat_df["crowding_rank"],
               alpha=0.4, s=15, color="#3498db")
    # Trend line
    if len(scat_df) > 10:
        z = np.polyfit(scat_df["eps_revision"], scat_df["crowding_rank"], 1)
        p = np.poly1d(z)
        xs = np.linspace(scat_df["eps_revision"].min(), scat_df["eps_revision"].max(), 100)
        ax.plot(xs, p(xs), "r--", linewidth=1.5, label="OLS fit")
        ax.legend()
    ax.set_xlabel("EPS Revision (winsorized)")
    ax.set_ylabel("Crowding Rank (percentile)")
    ax.set_title("Analyst Estimate Revision vs. Institutional Crowding")
    plt.tight_layout()
    fig.savefig(FIGURES / "revision_vs_crowding.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure 4: Time series — mean car_event for Q1 vs Q5
    ts_df = sort_df[sort_df["crowding_q"].isin([1.0, 5.0])].copy()
    ts    = (
        ts_df.groupby(["calendar_qtr_end", "crowding_q"])["car_event"]
        .mean()
        .unstack("crowding_q")
        .rename(columns={1.0: "Q1 (least crowded)", 5.0: "Q5 (most crowded)"})
        * 100
    )
    fig, ax = plt.subplots(figsize=(10, 4))
    for col in ts.columns:
        ax.plot(ts.index, ts[col], marker="o", label=col)
    ax.axhline(0, color="grey", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Quarter")
    ax.set_ylabel("Mean CAR[-1,+1] (%)")
    ax.set_title("Earnings CAR Over Time: Least vs Most Crowded")
    ax.legend()
    plt.xticks(rotation=45)
    plt.tight_layout()
    fig.savefig(FIGURES / "crowding_ts.png", dpi=150, bbox_inches="tight")
    plt.close()

    # Figure 5: Drift chart — car_drift by crowding quintile
    drift_df = df.dropna(subset=["crowding_q", "car_drift"])
    drift_q  = (
        drift_df.groupby("crowding_q")["car_drift"]
        .mean()
        .reset_index()
    )
    drift_q["car_drift_pct"] = drift_q["car_drift"] * 100
    fig, ax = plt.subplots(figsize=(7, 4))
    colors  = ["#2ecc71" if v > 0 else "#e74c3c" for v in drift_q["car_drift_pct"]]
    bars    = ax.bar(drift_q["crowding_q"].astype(str), drift_q["car_drift_pct"],
                     color=colors, edgecolor="white")
    ax.axhline(0, color="black", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Crowding Quintile (1=least, 5=most)")
    ax.set_ylabel("Mean post-earnings drift CAR[+2,+60] (%)")
    ax.set_title("Post-Earnings Drift by Crowding Quintile")
    ax.bar_label(bars, fmt="%.2f%%", padding=3, fontsize=9)
    plt.tight_layout()
    fig.savefig(FIGURES / "drift_by_quintile.png", dpi=150, bbox_inches="tight")
    plt.close()

    print(f"\nAll outputs saved to {OUTPUTS}")
    print(f"Figures saved to {FIGURES}")


if __name__ == "__main__":
    main()
