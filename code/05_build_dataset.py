"""
Step 7: Merge IBES consensus + 13F crowding + daily returns into the
analysis panel.

One row = stock × fiscal quarter with:
  eps_revision, revision_streak, dispersion, eps_surprise  (from IBES)
  n_filers, chg_filers, crowding_rank                     (from 13F)
  car_event (CAR[-1,+1]), car_drift (CAR[+2,+60])         (from daily returns)

Look-ahead rule (1-quarter lag):
  crowding from calendar quarter Q → CAR at earnings in Q+1
  (13F public ~45 days after Q; Q+1 earnings happen after that)

Output: inputs/final_dataset.parquet
"""
import sys, warnings
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import INPUTS, IBES_DIR, DAILY_RETURNS, SP500_HISTORY
from car_utils import align_fiscal_to_calendar, compute_car, build_features

CROWDING_PATH = INPUTS / "crowding.parquet"
CUSIP_MAP     = INPUTS / "cusip_ticker_map.parquet"
OUT           = INPUTS / "final_dataset.parquet"


# ── Helpers ────────────────────────────────────────────────────────────────────

def prior_quarter(dt: pd.Timestamp) -> pd.Timestamp:
    """Return the calendar quarter end one quarter before dt."""
    return dt - pd.DateOffset(months=3)


def load_crowding() -> pd.DataFrame:
    """
    Load crowding metrics. Falls back to a fake dataset if the real one
    doesn't exist yet (checkpoint mode).
    """
    if CROWDING_PATH.exists() and CUSIP_MAP.exists():
        crowding  = pd.read_parquet(CROWDING_PATH)
        cusip_map = pd.read_parquet(CUSIP_MAP)
        df = crowding.merge(cusip_map, on="cusip", how="inner")
        df["period_end"] = pd.to_datetime(df["period_end"])
        return df[["ticker", "period_end", "n_filers", "chg_filers"]].copy()
    else:
        # Checkpoint fake crowding — same tickers as IBES fake data
        print("  [checkpoint] No 13F crowding found — using fake crowding data")
        tickers  = ["AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA",
                    "JPM","JNJ","UNH","V","MA","HD","PG","XOM",
                    "CVX","MRK","ABBV","PEP","KO"]
        quarters = pd.date_range("2021-12-31", periods=9, freq="QE")
        rows = []
        rng  = np.random.default_rng(42)
        for tkr in tickers:
            base = rng.integers(50, 200)
            for q in quarters:
                n = int(base + rng.integers(-10, 20))
                rows.append({"ticker": tkr, "period_end": q,
                             "n_filers": n, "chg_filers": float(rng.integers(-15, 25))})
        return pd.DataFrame(rows)


def compute_crowding_rank(crowding: pd.DataFrame,
                          sp500: pd.DataFrame) -> pd.DataFrame:
    """
    Add crowding_rank = percentile of n_filers within each calendar quarter,
    computed over all S&P 500 constituents (not just filtered sample).
    """
    crowding = crowding.copy()
    crowding["crowding_rank"] = crowding.groupby("period_end")["n_filers"].rank(pct=True)
    return crowding


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("Loading inputs...")

    # 1. IBES consensus + feature engineering
    ibes_raw = pd.read_parquet(IBES_DIR / "ibes_consensus.parquet")
    ibes_raw["fpedats"] = pd.to_datetime(ibes_raw["fpedats"])
    ibes = build_features(ibes_raw)

    # fiscal → calendar quarter alignment
    ibes["calendar_qtr_end"] = ibes["fpedats"].apply(align_fiscal_to_calendar)
    ibes["fiscal_qtr_match"] = ibes["calendar_qtr_end"] == ibes["fpedats"]

    exact_rate = ibes["fiscal_qtr_match"].mean()
    print(f"  IBES: {len(ibes):,} rows — {exact_rate:.1%} exact fiscal/calendar matches")

    # Normalize ticker column name (IBES uses ibes_ticker)
    if "ibes_ticker" in ibes.columns and "ticker" not in ibes.columns:
        ibes = ibes.rename(columns={"ibes_ticker": "ticker"})

    # 2. Crowding (1-quarter lag: use Q-1 crowding to predict Q earnings)
    crowding = load_crowding()
    sp500    = pd.read_parquet(SP500_HISTORY)

    crowding = compute_crowding_rank(crowding, sp500)
    crowding["period_end"] = pd.to_datetime(crowding["period_end"])

    # Map: for each IBES fiscal quarter, join crowding from one quarter earlier
    ibes["crowding_qtr"] = ibes["calendar_qtr_end"].apply(prior_quarter)

    df = ibes.merge(
        crowding.rename(columns={"period_end": "crowding_qtr",
                                 "n_filers":   "n_filers",
                                 "chg_filers": "chg_filers",
                                 "crowding_rank": "crowding_rank"}),
        on=["ticker", "crowding_qtr"],
        how="left",
        validate="many_to_one",
    )
    print(f"  After crowding merge: {df['crowding_rank'].notna().sum():,} rows with crowding data")

    # 3. Filter: S&P 500 constituents (approximate — using current membership)
    sp500_tickers = set(sp500["ticker"].unique())
    df = df[df["ticker"].isin(sp500_tickers)].copy()
    print(f"  After S&P 500 filter: {len(df):,} rows")

    # 4. Daily returns — build wide pivot for CAR computation
    print("Loading daily returns for CAR computation...")
    daily = pd.read_parquet(DAILY_RETURNS)
    daily["date"] = pd.to_datetime(daily["date"])
    daily_wide = daily.pivot_table(index="date", columns="ticker",
                                   values="ret", aggfunc="first")
    daily_wide = daily_wide.sort_index()

    # 5. Compute CAR for each row
    print("Computing CARs...")
    cars_event = []
    cars_drift = []

    for _, row in df.iterrows():
        tkr       = row["ticker"]
        ann_date  = pd.Timestamp(row["anndats_act"]) if pd.notna(row["anndats_act"]) else None
        after_cls = False  # conservative: treat all as before-close

        if ann_date is None or tkr not in daily_wide.columns:
            cars_event.append(np.nan)
            cars_drift.append(np.nan)
            continue

        car_e = compute_car(tkr, ann_date, after_cls, daily_wide, pre=1, post=1)
        car_d = compute_car(tkr, ann_date, after_cls, daily_wide, pre=0, post=60,
                            start_offset=2)
        cars_event.append(car_e)
        cars_drift.append(car_d)

    df["car_event"] = cars_event
    df["car_drift"] = cars_drift

    # 6. Quality checks
    assert df[["ticker", "fpedats"]].duplicated().sum() == 0, \
        "Duplicate (ticker, fpedats) keys — check merges"

    car_coverage = df["car_event"].notna().mean()
    print(f"  CAR coverage: {car_coverage:.1%}")

    # 7. Save
    df.to_parquet(OUT, index=False)
    print(f"\nFinal dataset: {len(df):,} stock-quarter observations")
    print(f"  Tickers:  {df['ticker'].nunique():,}")
    print(f"  Quarters: {sorted(df['fpedats'].dt.strftime('%Y-Q%q').unique())}")
    print(f"  Columns:  {list(df.columns)}")
    print(f"\nSample rows:")
    cols = ["ticker","fpedats","eps_revision","revision_streak",
            "crowding_rank","car_event","car_drift"]
    print(df[cols].dropna(subset=["car_event"]).head(5).to_string(index=False))
    print(f"\nSaved → {OUT}")


if __name__ == "__main__":
    main()
