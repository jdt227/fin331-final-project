"""
Step 8. Package the results for the website (index.html, served by GitHub Pages).

Input : outputs/final_dataset.parquet, outputs/tables/*
Output: outputs/site_data.js   ->  window.SITE_DATA = {...}

The page reads ONLY this file, and this file is built ONLY from outputs/, so every
number on the website traces to a file in outputs/. It is a .js file (not .json) so
index.html also works when opened by double-clicking, without a web server.
"""
import json
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import safe_write_text, utc_now

T = config.TABLES


def records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


def table(name):
    return records(pd.read_csv(T / name))


d = pd.read_parquet(config.OUTPUTS / "final_dataset.parquet")
keep = ["quarter", "ticker", "issuer", "size_rank", "n_holders", "n_holders_lag",
        "pct_chg_holders", "dbreadth", "net_buyer_frac", "crowd_score",
        "formation_date", "holding_end_date", "ret_fwd", "exret_fwd"]
d = d[keep].copy()
for c in ["formation_date", "holding_end_date"]:
    d[c] = pd.to_datetime(d[c]).dt.strftime("%Y-%m-%d")
for c in ["pct_chg_holders", "dbreadth", "net_buyer_frac", "ret_fwd", "exret_fwd"]:
    d[c] = d[c].round(5)

site = {
    "generated_at_utc": utc_now(),
    "quick_mode": config.QUICK,
    "universe_size": config.UNIVERSE_SIZE,
    "primary_signal": config.PRIMARY_SIGNAL,
    "headline": json.loads((T / "headline_numbers.json").read_text(encoding="utf-8")),
    "quintiles": table("quintile_returns.csv"),
    "long_short_summary": table("long_short_summary.csv"),
    "long_short_by_quarter": table("long_short_by_quarter.csv"),
    "lookahead": table("lookahead_comparison.csv"),
    "magnitude": table("magnitude.csv"),
    "fama_macbeth": table("fama_macbeth.csv"),
    "pooled_ols": table("pooled_ols.csv"),
    "filing_counts": table("filing_filter_counts.csv"),
    "mapping": table("cusip_mapping_report.csv"),
    "exclusions": table("universe_exclusions.csv"),
    "coverage": table("return_coverage.csv"),
    "hand_checks": table("hand_checks.csv"),
    "specs": table("specs_run.csv"),
    "stocks": records(d),
}
out = config.OUTPUTS / "site_data.js"
safe_write_text(out, "window.SITE_DATA = " + json.dumps(site, separators=(",", ":")) + ";\n")
print(f"Wrote {out.name}: {len(d):,} stock-quarters, {out.stat().st_size / 1e3:.0f} KB")
print("Done.")
