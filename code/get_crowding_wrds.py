"""
Pull 13F institutional holdings from WRDS (Thomson Reuters / tfn.s34)
instead of scraping EDGAR directly.

tfn.s34:  one row per institution × stock × quarter
  mgrno   — manager number
  rdate   — report date (quarter end)
  cusip   — 8-digit CUSIP
  shares  — shares held (thousands)

Output: inputs/crowding.parquet
Columns: cusip, period_end, n_filers, chg_filers

Also saves: inputs/cusip_ticker_map.parquet (CUSIP → ticker via IBES link)
"""
import sys, warnings
import pandas as pd
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import INPUTS, START_YEAR, END_YEAR

OUT_CROWDING = INPUTS / "crowding.parquet"
OUT_MAP      = INPUTS / "cusip_ticker_map.parquet"


def pull_s34(db) -> pd.DataFrame:
    """Pull tfn.s34 holdings for our date range."""
    start = f"{START_YEAR - 1}-10-01"
    end   = f"{END_YEAR + 1}-03-31"
    sql = f"""
        SELECT rdate, cusip, mgrno, shares
        FROM tfn.s34
        WHERE rdate BETWEEN '{start}' AND '{end}'
          AND typecode = 1
          AND shares > 0
    """
    print("  Querying tfn.s34 (this may take a minute)...")
    df = db.raw_sql(sql, date_cols=["rdate"])
    return df


def build_crowding(s34: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate to (cusip, period_end):
      n_filers   = number of distinct institutions holding > 0 shares
      chg_filers = quarter-over-quarter change in n_filers
    """
    s34["period_end"] = pd.to_datetime(s34["rdate"]).dt.to_period("Q").dt.end_time.dt.normalize()

    agg = (
        s34.groupby(["cusip", "period_end"])["mgrno"]
        .nunique()
        .reset_index()
        .rename(columns={"mgrno": "n_filers"})
    )
    agg = agg.sort_values(["cusip", "period_end"])
    agg["chg_filers"] = agg.groupby("cusip")["n_filers"].diff()
    return agg


def build_cusip_ticker_map(db) -> pd.DataFrame:
    """
    Map 8-digit CUSIPs to tickers using IBES identifier crosswalk.
    Falls back to tfn.s34type for description if IBES link unavailable.
    """
    sql = """
        SELECT distinct ticker, ncusip as cusip
        FROM crsp.stocknames
        WHERE ncusip IS NOT NULL
          AND ticker IS NOT NULL
    """
    try:
        print("  Building CUSIP → ticker map from CRSP stocknames...")
        df = db.raw_sql(sql)
        df = df.dropna().drop_duplicates(subset=["cusip"])
        return df[["cusip", "ticker"]]
    except Exception as e:
        print(f"  CRSP stocknames failed ({e}); trying IBES link...")
        sql2 = """
            SELECT distinct ticker, cusip
            FROM ibes.idsum
            WHERE cusip IS NOT NULL AND ticker IS NOT NULL
        """
        df = db.raw_sql(sql2)
        df["cusip"] = df["cusip"].str[:8]
        df = df.dropna().drop_duplicates(subset=["cusip"])
        return df[["cusip", "ticker"]]


def main():
    if OUT_CROWDING.exists():
        df = pd.read_parquet(OUT_CROWDING)
        print(f"Crowding already exists: {len(df):,} rows — delete to re-pull")
        return

    import wrds
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        db = wrds.Connection()

    print("Connected to WRDS.")

    # 1. Holdings
    s34 = pull_s34(db)
    print(f"  Raw s34 rows: {len(s34):,}")

    # 2. Crowding aggregation
    crowding = build_crowding(s34)
    crowding.to_parquet(OUT_CROWDING, index=False)
    print(f"  Crowding saved: {len(crowding):,} cusip-quarter rows → {OUT_CROWDING}")

    # 3. CUSIP → ticker map
    if not OUT_MAP.exists():
        cmap = build_cusip_ticker_map(db)
        cmap.to_parquet(OUT_MAP, index=False)
        print(f"  CUSIP map saved: {len(cmap):,} entries → {OUT_MAP}")
    else:
        print(f"  CUSIP map already exists.")

    db.close()

    print(f"\nDone. Next: python code/05_build_dataset.py")


if __name__ == "__main__":
    main()
