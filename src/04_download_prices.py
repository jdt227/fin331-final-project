"""
Step 4. Daily split- and dividend-adjusted prices (and split events) from Yahoo Finance.

Input : data/interim/universe.parquet
Output: data/raw/prices_daily.parquet   long format: date, ticker, adj_close, split_ratio
        data/raw/prices_requests.csv    the date window requested for each ticker, so a
                                        ticker cached for a shorter window is re-pulled
        outputs/tables/price_coverage.csv

Known limitation (disclosed in README): Yahoo drops most delisted tickers, so stocks that
were acquired or went bankrupt after being in our universe may have no prices. The script
records exactly which universe tickers came back empty. Step 5 reports how many
stock-quarters lose their forward return because of this.
"""
import os
import sys
import time

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import log_provenance, utc_now

config.ensure_dirs()
universe = pd.read_parquet(config.INTERIM / "universe.parquet")
tickers = sorted(set(universe["ticker"]) | {config.MARKET_TICKER})

have = pd.read_parquet(config.PRICES) if config.PRICES.exists() else None
need_start, need_end = pd.Timestamp(config.PRICE_START), pd.Timestamp(config.PRICE_END)

# Which date window was requested for each cached ticker? A ticker cached for a SHORTER
# window (e.g. from the 2023-only v0 run) must be downloaded again, or the full-sample
# run would silently use a calendar that starts too late.
if config.PRICE_REQUESTS.exists():
    req = pd.read_csv(config.PRICE_REQUESTS, parse_dates=["start", "end"])
elif have is not None:   # cache made before this log existed: infer the window from the data
    req = (have.groupby("ticker")["date"].agg(start="min", end="max").reset_index()
               .assign(end=lambda x: x["end"] + pd.Timedelta(days=1),
                       pulled_at_utc="unknown (inferred from cached data)"))
    req["rows"] = req["ticker"].map(have.groupby("ticker").size())
else:
    req = pd.DataFrame(columns=["ticker", "start", "end", "pulled_at_utc", "rows"])
req = req.set_index("ticker")
covered = {t for t in req.index
           if req.at[t, "start"] <= need_start and req.at[t, "end"] >= need_end}
todo = [t for t in tickers if t not in covered]
print(f"{len(tickers)} tickers needed, {len(todo)} to download "
      f"({config.PRICE_START} to {config.PRICE_END})")

def fetch(chunk, threads):
    """Download a list of tickers; return long-format prices (possibly empty)."""
    df = yf.download(chunk, start=config.PRICE_START, end=config.PRICE_END,
                     auto_adjust=True, actions=True, progress=False,
                     group_by="column", threads=threads, multi_level_index=True)
    if df.empty:
        return pd.DataFrame(columns=["date", "ticker", "adj_close", "split_ratio"])
    close = df["Close"].stack(future_stack=True).rename("adj_close")
    if "Stock Splits" in df.columns.get_level_values(0):
        splits = df["Stock Splits"].stack(future_stack=True).rename("split_ratio")
    else:
        splits = (close * 0).rename("split_ratio")
    long = pd.concat([close, splits], axis=1).reset_index()
    long.columns = ["date", "ticker", "adj_close", "split_ratio"]
    return long.dropna(subset=["adj_close"])


# A re-downloaded ticker replaces ALL its old rows: adjusted prices pulled on different
# days use different dividend/split adjustment factors and must not be mixed.
frames = [] if have is None else [have[~have["ticker"].isin(todo)]]
got = set()
for i in range(0, len(todo), 100):
    chunk = todo[i:i + 100]
    long = fetch(chunk, threads=True)
    got |= set(long["ticker"])
    frames.append(long)
    print(f"  downloaded {i + len(chunk)}/{len(todo)}")

# Yahoo / yfinance sometimes fails one ticker for a transient reason (rate limit,
# "database is locked"). Retry each missing ticker on its own before calling it empty.
retry = [t for t in todo if t not in got]
for attempt in range(2):
    if not retry:
        break
    print(f"  retrying {len(retry)} tickers one at a time: {retry[:10]}")
    time.sleep(3)
    for t in retry:
        long = fetch([t], threads=False)
        if len(long):
            got.add(t)
            frames.append(long)
    retry = [t for t in retry if t not in got]
empty = set(retry)   # genuinely no data for this window (usually delisted)

if todo:
    prices = pd.concat(frames, ignore_index=True)
    prices["date"] = pd.to_datetime(prices["date"]).dt.tz_localize(None).dt.normalize()
    prices["split_ratio"] = prices["split_ratio"].fillna(0.0)
    prices = prices.drop_duplicates(["ticker", "date"], keep="last")
    prices.to_parquet(config.PRICES, index=False)
    now = utc_now()
    n_rows = prices.groupby("ticker").size()
    for t in todo:
        req.loc[t, ["start", "end", "pulled_at_utc", "rows"]] = \
            [need_start, need_end, now, int(n_rows.get(t, 0))]
    log_provenance("prices_daily.parquet", f"Yahoo Finance via yfinance {yf.__version__} "
                   "(auto_adjust=True, actions=True)", config.PRICES,
                   note=f"{prices['ticker'].nunique()} tickers; {len(empty)} returned no data")
else:
    prices = have
req.reset_index().rename(columns={"index": "ticker"}).to_csv(
    config.PRICE_REQUESTS, index=False, date_format="%Y-%m-%d")

assert not prices.duplicated(["ticker", "date"]).any()
cov = pd.DataFrame({"ticker": tickers})
cov["has_prices"] = cov["ticker"].isin(prices["ticker"])
cov.to_csv(config.TABLES / "price_coverage.csv", index=False)
print(f"Tickers with prices: {cov['has_prices'].sum()} / {len(cov)}. "
      f"Missing list: outputs/tables/price_coverage.csv")
print("Done.")
