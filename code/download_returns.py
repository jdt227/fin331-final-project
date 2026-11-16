"""
Download daily returns for all tickers in the current IBES dataset + SPY.
Run this once after get_ibes.py to fill in daily_returns.parquet.
"""
import sys, time
import pandas as pd
import yfinance as yf
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import INPUTS, DAILY_RETURNS, START_YEAR, END_YEAR

START = f"{START_YEAR - 1}-10-01"
END   = f"{END_YEAR + 1}-03-31"


def main():
    # Tickers we need
    ibes = pd.read_parquet(INPUTS / "ibes" / "ibes_consensus.parquet")
    need = set(ibes["ibes_ticker"].unique()) | {"SPY"}

    # Tickers we already have
    have = set()
    if DAILY_RETURNS.exists():
        existing = pd.read_parquet(DAILY_RETURNS)
        have = set(existing["ticker"].unique())
        print(f"Already have {len(have):,} tickers in daily_returns.parquet")
    else:
        existing = pd.DataFrame(columns=["date", "ticker", "ret"])

    missing = sorted(need - have)
    print(f"Need to download {len(missing):,} tickers ({START} → {END})")

    if not missing:
        print("Nothing to download.")
        return

    # Download in batches of 50 (yfinance handles batches well)
    BATCH = 50
    new_rows = []
    for i in range(0, len(missing), BATCH):
        batch = missing[i:i + BATCH]
        print(f"  Batch {i//BATCH + 1}/{(len(missing)-1)//BATCH + 1}: {batch[:3]}...")
        try:
            raw = yf.download(batch, start=START, end=END,
                              auto_adjust=True, progress=False, threads=True)
            if raw.empty:
                continue

            # yfinance returns MultiIndex columns when >1 ticker
            if isinstance(raw.columns, pd.MultiIndex):
                close = raw["Close"]
            else:
                close = raw[["Close"]]
                close.columns = [batch[0]]

            daily = close.pct_change().iloc[1:]
            long  = (
                daily.reset_index()
                .melt(id_vars="Date", var_name="ticker", value_name="ret")
                .rename(columns={"Date": "date"})
                .dropna(subset=["ret"])
            )
            long["date"] = pd.to_datetime(long["date"])
            new_rows.append(long)
        except Exception as e:
            print(f"    Error: {e}")
        time.sleep(0.5)

    if new_rows:
        new_df  = pd.concat(new_rows, ignore_index=True)
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=["date", "ticker"])
        combined.to_parquet(DAILY_RETURNS, index=False)
        print(f"\nSaved {len(combined):,} rows, {combined['ticker'].nunique():,} tickers → {DAILY_RETURNS}")
    else:
        print("No new data downloaded.")


if __name__ == "__main__":
    main()
