"""
Step 4: Map CUSIPs to tickers and download quarterly returns via yfinance.

CUSIP → ticker mapping uses the OpenFIGI API (free, no key needed for basic use).
  Endpoint: https://api.openfigi.com/v3/mapping
  Rate limit: 25 requests/min without an API key (each request = up to 100 CUSIPs)

Returns are downloaded as daily close prices, then resampled to quarterly.

Output:
  inputs/cusip_ticker_map.parquet   — CUSIP → ticker crosswalk
  inputs/returns/returns.parquet    — quarterly returns per ticker
"""
import sys, time, json, requests, yfinance as yf
import pandas as pd
from pathlib import Path
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).parent))
from config import START_YEAR, END_YEAR, INPUTS, RETURNS_DIR

OPENFIGI_URL   = "https://api.openfigi.com/v3/mapping"
OPENFIGI_DELAY = 2.5   # seconds between requests (25/min limit)
BATCH_SIZE     = 100   # max CUSIPs per OpenFIGI request
YF_DELAY       = 0.5   # seconds between yfinance downloads


# ── CUSIP → ticker mapping ─────────────────────────────────────────────────────

def map_cusips_to_tickers(cusips: list[str]) -> dict[str, str]:
    """Call OpenFIGI in batches; return {cusip: ticker}."""
    mapping = {}
    batches = [cusips[i:i + BATCH_SIZE] for i in range(0, len(cusips), BATCH_SIZE)]

    print(f"Mapping {len(cusips):,} CUSIPs via OpenFIGI ({len(batches)} batches)...")
    for batch in tqdm(batches, unit="batch"):
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            r = requests.post(
                OPENFIGI_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            if r.status_code == 429:
                print("  Rate limited — sleeping 60s")
                time.sleep(60)
                r = requests.post(OPENFIGI_URL, json=payload,
                                  headers={"Content-Type": "application/json"},
                                  timeout=30)
            r.raise_for_status()
            results = r.json()
        except Exception as e:
            print(f"  OpenFIGI error: {e}")
            time.sleep(OPENFIGI_DELAY)
            continue

        for cusip, result in zip(batch, results):
            data = result.get("data", [])
            if not data:
                continue
            # Prefer US equity listings
            us = [d for d in data if d.get("exchCode") in ("US", "UN", "UA", "UQ", "UP")]
            chosen = us[0] if us else data[0]
            ticker = chosen.get("ticker")
            if ticker:
                mapping[cusip] = ticker

        time.sleep(OPENFIGI_DELAY)

    return mapping


# ── Quarterly returns via yfinance ─────────────────────────────────────────────

def download_quarterly_returns(tickers: list[str]) -> pd.DataFrame:
    """
    Download daily prices for all tickers and compute quarterly returns.
    Quarter return = (last_close_in_quarter / last_close_in_prior_quarter) - 1
    """
    start = f"{START_YEAR - 1}-10-01"   # one extra quarter for the first diff
    end   = f"{END_YEAR + 1}-03-31"

    print(f"\nDownloading daily prices for {len(tickers):,} tickers...")
    all_prices = []

    for ticker in tqdm(tickers, unit="ticker"):
        try:
            df = yf.download(ticker, start=start, end=end,
                             auto_adjust=True, progress=False)
            if df.empty:
                continue
            close = df[["Close"]].copy()
            close.columns = [ticker]
            all_prices.append(close)
        except Exception:
            pass
        time.sleep(YF_DELAY)

    if not all_prices:
        raise ValueError("No price data downloaded.")

    prices = pd.concat(all_prices, axis=1)

    # Resample to last trading day of each quarter
    quarterly = prices.resample("QE").last()

    # Percent change quarter-over-quarter
    returns = quarterly.pct_change().iloc[1:]   # drop first NaN row

    # Melt wide → long
    ret_long = (
        returns.reset_index()
        .melt(id_vars="Date", var_name="ticker", value_name="ret")
        .rename(columns={"Date": "period_end"})
        .dropna(subset=["ret"])
    )
    ret_long["period_end"] = ret_long["period_end"].dt.strftime("%Y-%m-%d")

    return ret_long


def download_daily_returns(tickers: list[str]) -> pd.DataFrame:
    """
    Download and return daily adjusted-close pct changes for all tickers + SPY.
    Returns DataFrame(date, ticker, ret) — long format.
    """
    start = f"{START_YEAR - 1}-10-01"
    end   = f"{END_YEAR + 1}-03-31"
    all_tickers = list(set(tickers) | {"SPY"})

    print(f"\nDownloading daily prices for {len(all_tickers):,} tickers (incl. SPY)...")
    all_prices = []

    for ticker in tqdm(all_tickers, unit="ticker"):
        try:
            df = yf.download(ticker, start=start, end=end,
                             auto_adjust=True, progress=False)
            if df.empty:
                continue
            close = df[["Close"]].copy()
            close.columns = [ticker]
            all_prices.append(close)
        except Exception:
            pass
        time.sleep(YF_DELAY)

    if not all_prices:
        raise ValueError("No price data downloaded.")

    prices  = pd.concat(all_prices, axis=1)
    daily   = prices.pct_change().iloc[1:]  # daily returns

    ret_long = (
        daily.reset_index()
        .melt(id_vars="Date", var_name="ticker", value_name="ret")
        .rename(columns={"Date": "date"})
        .dropna(subset=["ret"])
    )
    ret_long["date"] = pd.to_datetime(ret_long["date"])
    return ret_long


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    crowding_path = INPUTS / "crowding.parquet"
    if not crowding_path.exists():
        raise FileNotFoundError("Run 03_build_crowding.py first.")

    crowding = pd.read_parquet(crowding_path)
    all_cusips = crowding["cusip"].unique().tolist()

    # --- CUSIP → ticker ---
    map_path = INPUTS / "cusip_ticker_map.parquet"
    if map_path.exists():
        cusip_map = pd.read_parquet(map_path)
        print(f"Loaded existing CUSIP map ({len(cusip_map):,} entries)")
    else:
        mapping = map_cusips_to_tickers(all_cusips)
        cusip_map = pd.DataFrame(
            list(mapping.items()), columns=["cusip", "ticker"]
        )
        cusip_map.to_parquet(map_path, index=False)
        print(f"Mapped {len(cusip_map):,} of {len(all_cusips):,} CUSIPs")

    print("\nSample CUSIP → ticker mappings (verify these look right):")
    print(cusip_map.sample(min(10, len(cusip_map))).to_string(index=False))

    tickers = cusip_map["ticker"].unique().tolist()

    # --- Quarterly returns ---
    ret_path = RETURNS_DIR / "returns.parquet"
    if ret_path.exists():
        print(f"\nLoaded existing quarterly returns file")
    else:
        ret_long = download_quarterly_returns(tickers)
        ret_long.to_parquet(ret_path, index=False)
        print(f"Quarterly returns saved: {len(ret_long):,} rows")

    # --- Daily returns (needed for CAR event studies) ---
    daily_path = RETURNS_DIR / "daily_returns.parquet"
    if daily_path.exists():
        print(f"Loaded existing daily returns file")
    else:
        daily = download_daily_returns(tickers)
        daily.to_parquet(daily_path, index=False)
        print(f"Daily returns saved: {len(daily):,} rows")


if __name__ == "__main__":
    main()
