"""
Step 5. Build the final analysis dataset: one row per stock x signal quarter.

Input : data/interim/{universe, cusip_quarter_stats, filings}.parquet
        data/interim/holdings/<quarter>.parquet
        data/raw/prices_daily.parquet
Output: outputs/final_dataset.csv (+ .parquet)
        outputs/tables/return_coverage.csv
        outputs/tables/sample_rows.md          paste these real rows into PROPOSAL.md

Timing (the core of the project):
  quarter q holdings  -> public by filing_deadline(q) = quarter end + 45 days
  formation_date(q)   =  first trading day AFTER the deadline (buy at that close)
  ret_fwd             =  close-to-close return from formation_date(q) to formation_date(q+1)
  ret_naive           =  quarter end q -> quarter end q+1. This is the LOOK-AHEAD version:
                         it starts before the holdings were public. Kept ONLY to show
                         how much the timing mistake would matter.

Crowding measures for stock i, quarter q:
  n_holders        number of 13F managers holding i at end of q
  pct_chg_holders  n_holders(q) / n_holders(q-1) - 1
  dbreadth         Chen, Hong & Stein (2002) change in breadth: among managers who filed
                   in BOTH q-1 and q, (#holding at q - #holding at q-1) / #such managers,
                   in percentage points. Using only continuing filers removes the
                   mechanical effect of new managers entering the 13F data.   [PRIMARY]
  net_buyer_frac   among continuing managers that hold i at q-1 or q:
                   (#buyers - #sellers) / (#buyers + #sellers), with q-1 shares adjusted
                   for stock splits between the two quarter ends.
  crowd_score      dashboard score, 0-100: mean of the within-quarter percentile ranks
                   of n_holders and dbreadth. Descriptive only, not a tested signal.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import qstr

config.ensure_dirs()
universe = pd.read_parquet(config.INTERIM / "universe.parquet")
stats = pd.read_parquet(config.INTERIM / "cusip_quarter_stats.parquet")
filings = pd.read_parquet(config.INTERIM / "filings.parquet")
prices = pd.read_parquet(config.PRICES)

# ---------------------------------------------------------------- prices, wide
px = prices.pivot(index="date", columns="ticker", values="adj_close").sort_index()
cal = px[config.MARKET_TICKER].dropna().index          # trading calendar = SPY days
px = px.reindex(cal).ffill(limit=5)                    # bridge short gaps only
splits = prices.pivot(index="date", columns="ticker", values="split_ratio").reindex(cal)
splits = splits.where(splits > 0, 1.0).fillna(1.0)


def formation_date(q):
    d = config.filing_deadline(q)
    after = cal[cal > d]
    if len(after) == 0:
        raise ValueError(f"No prices after {d.date()} for {q}; extend PRICE_END")
    return after[0]


def last_close_on_or_before(d):
    return cal[cal <= d][-1]


def price(ticker, d):
    if ticker not in px.columns:
        return np.nan
    return px.at[d, ticker]


def split_factor(ticker, q_prev, q):
    """Shares at end of q_prev x factor = comparable shares at end of q."""
    if ticker not in splits.columns:
        return 1.0
    a, b = config.quarter_end(q_prev), config.quarter_end(q)
    s = splits.loc[(splits.index > a) & (splits.index <= b), ticker]
    return float(s.prod())


def load_holdings(q, cusips, ciks):
    h = pd.read_parquet(config.INTERIM / "holdings" / f"{qstr(q)}.parquet",
                        columns=["cik", "cusip", "shares"])
    return h[h["cusip"].isin(cusips) & h["cik"].isin(ciks)]


rows = []
for q in config.SIGNAL_QUARTERS:
    qs, qp = qstr(q), q - 1
    u = universe[universe["quarter"] == qs].copy()
    cus = set(u["cusip"])

    # --- holder counts (all managers) and their lag
    s_now = stats[stats["quarter"] == qs].set_index("cusip")
    s_lag = stats[stats["quarter"] == qstr(qp)].set_index("cusip")
    u = u.join(s_now[["n_holders", "n_filers_total"]], on="cusip", validate="1:1")
    u = u.join(s_lag[["n_holders"]].rename(columns={"n_holders": "n_holders_lag"}),
               on="cusip", validate="1:1")
    u["pct_chg_holders"] = u["n_holders"] / u["n_holders_lag"] - 1

    # --- continuing managers: filed in both q-1 and q
    cont = set(filings.loc[filings["quarter"] == qs, "cik"]) & \
        set(filings.loc[filings["quarter"] == qstr(qp), "cik"])
    h_now = load_holdings(q, cus, cont)
    h_lag = load_holdings(qp, cus, cont)
    b_now = h_now.groupby("cusip")["cik"].nunique()
    b_lag = h_lag.groupby("cusip")["cik"].nunique()
    u["n_continuing_filers"] = len(cont)
    u["breadth"] = u["cusip"].map(b_now).fillna(0) / len(cont) * 100
    u["breadth_lag"] = u["cusip"].map(b_lag).fillna(0) / len(cont) * 100
    u["dbreadth"] = u["breadth"] - u["breadth_lag"]

    # --- buyers vs sellers among continuing managers (split-adjusted)
    m = h_now.merge(h_lag, on=["cik", "cusip"], how="outer", suffixes=("", "_lag"),
                    validate="1:1").fillna({"shares": 0, "shares_lag": 0})
    tick = u.set_index("cusip")["ticker"]
    fac = {c: split_factor(tick[c], qp, q) for c in cus}
    m["shares_lag_adj"] = m["shares_lag"] * m["cusip"].map(fac)
    m["buy"] = m["shares"] > m["shares_lag_adj"] * 1.001
    m["sell"] = m["shares"] < m["shares_lag_adj"] * 0.999
    bs = m.groupby("cusip")[["buy", "sell"]].sum()
    u = u.join(bs, on="cusip", validate="1:1")
    u["net_buyer_frac"] = (u["buy"] - u["sell"]) / (u["buy"] + u["sell"])
    u["split_factor"] = u["cusip"].map(fac)

    # --- dates and returns
    f0, f1, fm1 = formation_date(q), formation_date(q + 1), formation_date(qp)
    e0, e1 = last_close_on_or_before(config.quarter_end(q)), \
        last_close_on_or_before(config.quarter_end(q + 1))
    u["quarter_end"] = config.quarter_end(q)
    u["filing_deadline"] = config.filing_deadline(q)
    u["formation_date"] = f0
    u["holding_end_date"] = f1
    mkt = lambda a, b: price(config.MARKET_TICKER, b) / price(config.MARKET_TICKER, a) - 1
    u["ret_fwd"] = [price(t, f1) / price(t, f0) - 1 for t in u["ticker"]]
    u["mkt_fwd"] = mkt(f0, f1)
    u["ret_naive"] = [price(t, e1) / price(t, e0) - 1 for t in u["ticker"]]
    u["mkt_naive"] = mkt(e0, e1)
    u["ret_past"] = [price(t, f0) / price(t, fm1) - 1 for t in u["ticker"]]
    win = px.loc[:f0].tail(64)
    vol = win.pct_change(fill_method=None).iloc[1:].std() * np.sqrt(252)
    u["vol_63d"] = u["ticker"].map(vol)
    rows.append(u)

d = pd.concat(rows, ignore_index=True)
d["exret_fwd"] = d["ret_fwd"] - d["mkt_fwd"]
d["exret_naive"] = d["ret_naive"] - d["mkt_naive"]
d["log_inst_dollar"] = np.log(d["inst_dollar"])
pr = lambda col: d.groupby("quarter")[col].rank(pct=True)
d["crowd_score"] = ((pr("n_holders") + pr("dbreadth")) / 2 * 100).round(1)

cols = ["quarter", "ticker", "cusip", "issuer", "size_rank", "inst_dollar",
        "log_inst_dollar", "n_filers_total", "n_continuing_filers", "n_holders",
        "n_holders_lag", "pct_chg_holders", "breadth", "breadth_lag", "dbreadth", "buy",
        "sell", "net_buyer_frac", "split_factor", "crowd_score", "quarter_end",
        "filing_deadline", "formation_date", "holding_end_date", "ret_fwd", "mkt_fwd",
        "exret_fwd", "ret_naive", "mkt_naive", "exret_naive", "ret_past", "vol_63d"]
d = d[cols].sort_values(["quarter", "size_rank"]).reset_index(drop=True)
assert not d.duplicated(["ticker", "quarter"]).any(), "ticker-quarter must be unique"
assert not d.duplicated(["cusip", "quarter"]).any(), "cusip-quarter must be unique"
assert (d["formation_date"] > d["filing_deadline"]).all(), "formation must follow deadline"
d.to_parquet(config.OUTPUTS / "final_dataset.parquet", index=False)
d.to_csv(config.OUTPUTS / "final_dataset.csv", index=False)

cov = d.groupby("quarter").agg(stocks=("ticker", "size"),
                               with_fwd_return=("ret_fwd", "count"),
                               with_dbreadth=("dbreadth", "count"))
cov["share_missing_return"] = 1 - cov["with_fwd_return"] / cov["stocks"]
cov.to_csv(config.TABLES / "return_coverage.csv")
print(cov.to_string())

# ---------------------------------------------------------------- sample rows for PROPOSAL.md
show = ["quarter", "ticker", "n_holders", "n_holders_lag", "dbreadth", "net_buyer_frac",
        "crowd_score", "formation_date", "ret_fwd", "exret_fwd"]
qmid = config.SIGNAL_QUARTERS[len(config.SIGNAL_QUARTERS) // 2]
pref = ["AAPL", "NVDA", "JPM", "XOM", "TSLA"]
sample = d[(d["quarter"] == qstr(qmid)) & d["ticker"].isin(pref)]
if len(sample) < 3:
    sample = d[d["quarter"] == qstr(qmid)].head(5)
sample = sample[show].copy()
sample["formation_date"] = sample["formation_date"].dt.strftime("%Y-%m-%d")
for c in ["dbreadth", "net_buyer_frac", "ret_fwd", "exret_fwd"]:
    sample[c] = sample[c].round(3)
md = "| " + " | ".join(show) + " |\n|" + "---|" * len(show) + "\n"
md += "\n".join("| " + " | ".join(str(v) for v in r) + " |" for r in sample.values)
(config.TABLES / "sample_rows.md").write_text(md + "\n")
print(f"\nFinal dataset: {len(d):,} stock-quarters, {d['ticker'].nunique()} tickers, "
      f"{d['quarter'].nunique()} quarters")
print("Done.")
