"""
Step 4. Daily split- and dividend-adjusted prices (and split events) from Yahoo Finance.

Input : data/interim/universe.parquet
Output: data/raw/prices_daily.parquet   long format: date, ticker, adj_close, split_ratio
        outputs/tables/price_coverage.csv

Known limitation (disclosed in README): Yahoo drops most delisted tickers, so stocks that
were acquired or went bankrupt after being in our universe may have no prices. The script
records exactly which universe tickers came back empty. Step 5 reports how many
stock-quarters lose their forward return because of this.
"""
import os
import sys

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import log_provenance

config.ensure_dirs()
universe = pd.read_parquet(config.INTERIM / "universe.parquet")
tickers = sorted(set(universe["ticker"]) | {config.MARKET_TICKER})

have = pd.read_parquet(config.PRICES) if config.PRICES.exists() else None
done = set(have["ticker"]) if have is not None else set()
tried_file = config.RAW / "prices_tried_empty.txt"
tried_empty = set(tried_file.read_text().split()) if tried_file.exists() else set()
todo = [t for t in tickers if t not in done and t not in tried_empty]
print(f"{len(tickers)} tickers needed, {len(todo)} to download "
      f"({config.PRICE_START} to {config.PRICE_END})")

frames = [] if have is None else [have]
empty = set(tried_empty)
for i in range(0, len(todo), 100):
    chunk = todo[i:i + 100]
    df = yf.download(chunk, start=config.PRICE_START, end=config.PRICE_END,
                     auto_adjust=True, actions=True, progress=False,
                     group_by="column", threads=True, multi_level_index=True)
    if df.empty:
        empty |= set(chunk)
        continue
    close = df["Close"].stack(future_stack=True).rename("adj_close")
    if "Stock Splits" in df.columns.get_level_values(0):
        splits = df["Stock Splits"].stack(future_stack=True).rename("split_ratio")
    else:
        splits = (close * 0).rename("split_ratio")
    long = pd.concat([close, splits], axis=1).reset_index()
    long.columns = ["date", "ticker", "adj_close", "split_ratio"]
    long = long.dropna(subset=["adj_close"])
    empty |= set(chunk) - set(long["ticker"])
    frames.append(long)
    print(f"  downloaded {i + len(chunk)}/{len(todo)}")

if todo:
    prices = pd.concat(frames, ignore_index=True)
    prices["date"] = pd.to_datetime(prices["date"]).dt.tz_localize(None).dt.normalize()
    prices["split_ratio"] = prices["split_ratio"].fillna(0.0)
    prices = prices.drop_duplicates(["ticker", "date"], keep="last")
    prices.to_parquet(config.PRICES, index=False)
    tried_file.write_text("\n".join(sorted(empty)))
    log_provenance("prices_daily.parquet", f"Yahoo Finance via yfinance {yf.__version__} "
                   "(auto_adjust=True, actions=True)", config.PRICES,
                   note=f"{prices['ticker'].nunique()} tickers; {len(empty)} returned no data")
else:
    prices = have

assert not prices.duplicated(["ticker", "date"]).any()
cov = pd.DataFrame({"ticker": tickers})
cov["has_prices"] = cov["ticker"].isin(prices["ticker"])
cov.to_csv(config.TABLES / "price_coverage.csv", index=False)
print(f"Tickers with prices: {cov['has_prices'].sum()} / {len(cov)}. "
      f"Missing list: outputs/tables/price_coverage.csv")
print("Done.")
