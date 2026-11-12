"""
Step 3: Aggregate raw holdings into crowding metrics per stock per quarter.

For each (period_end, cusip):
  n_filers       = number of unique 13F filers holding the stock
  chg_filers     = quarter-over-quarter change in n_filers
  info_date      = latest date_filed in that quarter (the day info is fully public)

Look-ahead safeguard: info_date = max(date_filed) across all filers in the
quarter.  Returns are only computed from this date onward in later steps.

Output: inputs/crowding.parquet
"""
import sys, pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import QUARTERS, HOLDINGS_DIR, INPUTS, MIN_HOLDER_COUNT


def main():
    frames = []
    for year, qtr in QUARTERS:
        p = HOLDINGS_DIR / f"holdings_{year}_Q{qtr}.parquet"
        if p.exists():
            frames.append(pd.read_parquet(p))
        else:
            print(f"  Warning: {p.name} not found — skipping")

    if not frames:
        raise FileNotFoundError(
            "No holdings files found. Run 02_get_holdings.py first."
        )

    raw = pd.concat(frames, ignore_index=True)
    raw["date_filed"] = pd.to_datetime(raw["date_filed"])

    # Count unique filers per (period_end, cusip)
    crowding = (
        raw.groupby(["period_end", "cusip"])
        .agg(
            n_filers =("cik",         "nunique"),
            info_date=("date_filed",  "max"),   # fully public after last filer submits
        )
        .reset_index()
    )

    # Remove thinly covered stocks
    crowding = crowding[crowding["n_filers"] >= MIN_HOLDER_COUNT].copy()

    # Quarter-over-quarter change in filer count
    crowding = crowding.sort_values(["cusip", "period_end"])
    crowding["chg_filers"] = crowding.groupby("cusip")["n_filers"].diff()

    # Normalise by total filers that quarter so scale doesn't drift over time
    total_filers = (
        raw.groupby("period_end")["cik"]
        .nunique()
        .rename("total_filers")
        .reset_index()
    )
    crowding = crowding.merge(total_filers, on="period_end", how="left")
    crowding["frac_filers"] = crowding["n_filers"] / crowding["total_filers"]
    crowding["chg_frac"]    = crowding.groupby("cusip")["frac_filers"].diff()

    out = INPUTS / "crowding.parquet"
    crowding.to_parquet(out, index=False)

    print(f"Crowding dataset: {len(crowding):,} rows, {crowding['cusip'].nunique():,} unique CUSIPs")
    print(f"Quarters covered: {sorted(crowding['period_end'].unique())}")
    print(f"Saved → {out}")


if __name__ == "__main__":
    main()
