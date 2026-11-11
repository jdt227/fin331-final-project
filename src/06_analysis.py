"""
Step 6. Sorts, regressions, magnitudes, figures.

Input : outputs/final_dataset.parquet
Output: outputs/tables/quintile_returns.csv      mean next-quarter excess return by quintile
        outputs/tables/long_short_by_quarter.csv Q5-Q1 (most minus least crowded) per quarter
        outputs/tables/long_short_summary.csv    mean, t-stat, hit rate per signal
        outputs/tables/lookahead_comparison.csv  correct timing vs quarter-end timing
        outputs/tables/fama_macbeth.csv          FM regressions with controls
        outputs/tables/pooled_ols.csv            pooled OLS, quarter FE, SE clustered by stock
        outputs/tables/magnitude.csv             spread after turnover-based trading costs
        outputs/tables/headline_numbers.json     numbers quoted in README / dashboard
        outputs/tables/specs_run.csv             automatic log of every spec run (p-hacking audit)
        outputs/figures/*.png

Quintile rule (used everywhere, re-implemented by hand in step 7):
  within each quarter, rank the signal with ties broken by order (method='first'),
  bin = ceil(rank * 5 / n). Bin 5 = most crowded.
"""
import json
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

sys.path.insert(0, os.path.dirname(__file__))
import config

config.ensure_dirs()
d = pd.read_parquet(config.OUTPUTS / "final_dataset.parquet")
specs = []


def add_bins(df, signal, n=config.N_BINS):
    df = df.dropna(subset=[signal]).copy()
    r = df.groupby("quarter")[signal].rank(method="first")
    cnt = df.groupby("quarter")[signal].transform("count")
    df["bin"] = np.ceil(r * n / cnt).astype(int)
    return df


def tstat(x):
    x = pd.Series(x).dropna()
    return x.mean() / (x.std(ddof=1) / np.sqrt(len(x))) if len(x) > 1 else np.nan


def sort_results(signal, ret):
    df = add_bins(d.dropna(subset=[ret]), signal)
    by_q = df.groupby(["quarter", "bin"])[ret].mean().unstack()
    ls = (by_q[config.N_BINS] - by_q[1]).rename("long_short")
    specs.append({"method": "quintile sort", "signal": signal, "return": ret,
                  "controls": "none", "n_quarters": len(ls), "estimate": ls.mean(),
                  "t_stat": tstat(ls)})
    return df, by_q, ls


# ---------------------------------------------------------------- 1. sorts
qrows, lsrows, summ = [], [], []
for sig in config.SIGNALS:
    df, by_q, ls = sort_results(sig, "exret_fwd")
    m = by_q.mean()
    for b in m.index:
        qrows.append({"signal": sig, "quintile": b, "mean_exret_fwd": m[b],
                      "t_stat": tstat(by_q[b]),
                      "avg_stocks": df[df["bin"] == b].groupby("quarter").size().mean()})
    for q, v in ls.items():
        lsrows.append({"signal": sig, "quarter": q, "long_short": v})
    summ.append({"signal": sig, "mean_q5_minus_q1": ls.mean(), "t_stat": tstat(ls),
                 "share_quarters_positive": (ls > 0).mean(), "n_quarters": len(ls),
                 "primary": sig == config.PRIMARY_SIGNAL})
pd.DataFrame(qrows).to_csv(config.TABLES / "quintile_returns.csv", index=False)
pd.DataFrame(lsrows).to_csv(config.TABLES / "long_short_by_quarter.csv", index=False)
summary = pd.DataFrame(summ)
summary.to_csv(config.TABLES / "long_short_summary.csv", index=False)
print(summary.round(4).to_string(index=False))

# ---------------------------------------------------------------- 2. look-ahead comparison
la = []
for ret in ["exret_fwd", "exret_naive"]:
    _, by_q, ls = sort_results(config.PRIMARY_SIGNAL, ret)
    if ret == "exret_fwd":
        specs.pop()  # same as the primary sort already logged above
    la.append({"timing": "filing-date (correct)" if ret == "exret_fwd"
               else "quarter-end (look-ahead)", "return_column": ret,
               "mean_q5_minus_q1": ls.mean(), "t_stat": tstat(ls)})
pd.DataFrame(la).to_csv(config.TABLES / "lookahead_comparison.csv", index=False)

# ---------------------------------------------------------------- 3. regressions
controls = ["ret_past", "vol_63d", "log_inst_dollar"]
fm_rows, ols_rows = [], []
for sig in config.SIGNALS:
    cols = [sig] + controls
    r = d.dropna(subset=cols + ["exret_fwd"]).copy()
    # standardize within quarter so a coefficient = return per 1 SD of the variable
    for c in cols:
        r[c + "_z"] = r.groupby("quarter")[c].transform(lambda x: (x - x.mean()) / x.std())
    zc = [c + "_z" for c in cols]
    coefs = []
    for q, g in r.groupby("quarter"):
        X = np.column_stack([np.ones(len(g))] + [g[c].values for c in zc])
        b, *_ = np.linalg.lstsq(X, g["exret_fwd"].values, rcond=None)
        coefs.append(b)
    coefs = pd.DataFrame(coefs, columns=["const"] + cols)
    for c in coefs.columns:
        fm_rows.append({"signal": sig, "variable": c, "coef": coefs[c].mean(),
                        "t_stat": tstat(coefs[c]), "n_quarters": len(coefs),
                        "avg_n_stocks": len(r) / len(coefs)})
    specs.append({"method": "Fama-MacBeth", "signal": sig, "return": "exret_fwd",
                  "controls": "+".join(controls), "n_quarters": len(coefs),
                  "estimate": coefs[sig].mean(), "t_stat": tstat(coefs[sig])})
    fit = smf.ols(f"exret_fwd ~ {' + '.join(zc)} + C(quarter)", data=r).fit(
        cov_type="cluster", cov_kwds={"groups": pd.factorize(r["ticker"])[0]})
    for c in zc:
        ols_rows.append({"signal": sig, "variable": c, "coef": fit.params[c],
                         "t_stat": fit.tvalues[c], "n_obs": int(fit.nobs),
                         "r2": fit.rsquared})
    specs.append({"method": "pooled OLS, quarter FE, cluster by stock", "signal": sig,
                  "return": "exret_fwd", "controls": "+".join(controls),
                  "n_quarters": r["quarter"].nunique(), "estimate": fit.params[sig + "_z"],
                  "t_stat": fit.tvalues[sig + "_z"]})
pd.DataFrame(fm_rows).to_csv(config.TABLES / "fama_macbeth.csv", index=False)
pd.DataFrame(ols_rows).to_csv(config.TABLES / "pooled_ols.csv", index=False)

# ---------------------------------------------------------------- 4. magnitude after costs
df = add_bins(d.dropna(subset=["exret_fwd"]), config.PRIMARY_SIGNAL)
qs = sorted(df["quarter"].unique())
turn = []
for a, b in zip(qs[:-1], qs[1:]):
    for leg in [1, config.N_BINS]:
        A = set(df[(df["quarter"] == a) & (df["bin"] == leg)]["ticker"])
        B = set(df[(df["quarter"] == b) & (df["bin"] == leg)]["ticker"])
        turn.append(1 - len(A & B) / max(len(B), 1))   # share of the leg replaced
avg_turn = float(np.mean(turn)) if turn else 1.0
gross = summary.set_index("signal").loc[config.PRIMARY_SIGNAL, "mean_q5_minus_q1"]
# each quarter, each leg replaces `avg_turn` of its names: sell + buy = 2 trades
cost = 2 * avg_turn * 2 * config.COST_BPS_PER_SIDE / 1e4
mag = pd.DataFrame([{
    "signal": config.PRIMARY_SIGNAL, "gross_q5_minus_q1_per_quarter": gross,
    "avg_leg_turnover_per_quarter": avg_turn, "cost_bps_per_side": config.COST_BPS_PER_SIDE,
    "cost_per_quarter": cost, "net_per_quarter": gross - cost,
    "net_annualized_approx": (1 + gross - cost) ** 4 - 1}])
mag.to_csv(config.TABLES / "magnitude.csv", index=False)

# ---------------------------------------------------------------- 5. figures
prim = pd.DataFrame(qrows).query("signal == @config.PRIMARY_SIGNAL")
_, by_naive, _ = sort_results(config.PRIMARY_SIGNAL, "exret_naive")
specs.pop()  # duplicate of the look-ahead spec already logged
fig, ax = plt.subplots(figsize=(7, 4))
x = np.arange(1, config.N_BINS + 1)
ax.bar(x - 0.2, prim["mean_exret_fwd"] * 100, width=0.4, label="Filing-date timing (correct)")
ax.bar(x + 0.2, by_naive.mean().values * 100, width=0.4, color="#bbbbbb",
       label="Quarter-end timing (look-ahead)")
ax.axhline(0, color="black", lw=0.8)
ax.set_xticks(x, ["Q1\nleast crowded", "Q2", "Q3", "Q4", "Q5\nmost crowded"])
ax.set_ylabel("Avg next-quarter return minus SPY (%)")
ax.set_title(f"Next-quarter excess return by crowding quintile ({config.PRIMARY_SIGNAL})")
ax.legend(frameon=False, fontsize=8)
fig.tight_layout()
fig.savefig(config.FIGURES / "quintile_returns.png", dpi=150)
plt.close(fig)

ls = pd.DataFrame(lsrows).query("signal == @config.PRIMARY_SIGNAL").sort_values("quarter")
fig, ax = plt.subplots(figsize=(7, 4))
ax.plot(ls["quarter"], (1 + ls["long_short"]).cumprod() - 1, marker="o")
ax.axhline(0, color="black", lw=0.8)
ax.set_ylabel("Cumulative Q5 - Q1 return")
ax.set_title("Long most-crowded, short least-crowded (gross)")
ax.tick_params(axis="x", rotation=45)
fig.tight_layout()
fig.savefig(config.FIGURES / "cumulative_long_short.png", dpi=150)
plt.close(fig)

# ---------------------------------------------------------------- 6. logs + headline numbers
pd.DataFrame(specs).to_csv(config.TABLES / "specs_run.csv", index=False)
p = summary.set_index("signal").loc[config.PRIMARY_SIGNAL]
head = {
    "sample_quarters": f"{d['quarter'].min()} to {d['quarter'].max()}",
    "n_stock_quarters": int(len(d)),
    "n_with_forward_return": int(d["exret_fwd"].notna().sum()),
    "primary_signal": config.PRIMARY_SIGNAL,
    "primary_q5_minus_q1_per_quarter": float(p["mean_q5_minus_q1"]),
    "primary_t_stat": float(p["t_stat"]),
    "primary_net_of_costs_per_quarter": float(mag["net_per_quarter"].iloc[0]),
    "n_specifications_run": len(specs),
}
(config.TABLES / "headline_numbers.json").write_text(json.dumps(head, indent=2))
print(json.dumps(head, indent=2))
print("Done.")
