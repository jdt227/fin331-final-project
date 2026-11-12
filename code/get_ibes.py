"""
Step 2: Pull IBES analyst consensus data from WRDS.

NOTE FOR CHECKPOINT: inputs/ibes/ibes_consensus.parquet is currently a
20-ticker fake dataset used to run the full pipeline end-to-end.
To replace it with real IBES data:
  1. Install wrds in a Python 3.10/3.11 environment:
       conda create -n wrds311 python=3.11 && conda activate wrds311
       pip install wrds pandas pyarrow
  2. Run:  python code/get_ibes.py
     (delete inputs/ibes/ibes_consensus.parquet first to force re-pull)
  3. Log in with your WRDS username when prompted.

For each (ticker, fiscal-period-end), we need two EPS consensus snapshots:
  - snapshot_t:   the consensus measured at the end of the target fiscal quarter
  - snapshot_tm1: the consensus measured ~one quarter earlier (91 days before)

This gives us eps_revision = how much the consensus for THIS quarter's EPS
changed between the two snapshot dates — the standard "revision" definition.

Output: inputs/ibes/ibes_consensus.parquet
Columns:
  ibes_ticker, fpedats, eps_consensus_t, eps_consensus_tm1,
  dispersion_t, n_analysts_t, eps_actual, anndats_act
"""
import sys, warnings
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from config import IBES_DIR, START_YEAR, END_YEAR

OUT = IBES_DIR / "ibes_consensus.parquet"


def pull_ibes_raw() -> pd.DataFrame:
    """
    Connect to WRDS and pull ibes.statsum_epsus for quarterly US EPS.
    Returns raw statsum rows with columns:
      ticker, fpedats, statpers, meanest, stdev, numest, actual, anndats_act
    """
    import wrds
    db = wrds.Connection()

    # fpi='6' in IBES statsum_epsus = current fiscal quarter (1-quarter ahead)
    # statpers = the date the consensus snapshot was taken (monthly)
    # fpedats  = the fiscal period end date (the target quarter)
    sql = f"""
        SELECT ticker, fpedats, statpers, meanest, stdev, numest, actual, anndats_act
        FROM ibes.statsum_epsus
        WHERE fpi = '6'
          AND measure = 'EPS'
          AND curcode = 'USD'
          AND usfirm = 1
          AND fpedats BETWEEN '{START_YEAR - 1}-10-01' AND '{END_YEAR + 1}-03-31'
    """
    df = db.raw_sql(sql, date_cols=["fpedats", "statpers", "anndats_act"])
    db.close()
    return df


def build_consensus_snapshots(raw: pd.DataFrame) -> pd.DataFrame:
    """
    For each (ticker, fpedats), extract two statpers snapshots:
      snapshot_t   = statpers closest to fpedats (but ≤ fpedats)
      snapshot_tm1 = statpers closest to (fpedats - 91 days)

    Returns one row per (ticker, fpedats).
    """
    raw = raw.copy()
    raw["fpedats"]  = pd.to_datetime(raw["fpedats"])
    raw["statpers"] = pd.to_datetime(raw["statpers"])

    rows = []
    for (ticker, fpedats), grp in raw.groupby(["ticker", "fpedats"]):
        grp = grp.sort_values("statpers")

        target_t   = fpedats
        target_tm1 = fpedats - pd.Timedelta(days=91)

        # snapshot_t: closest statpers ≤ fpedats
        valid_t = grp[grp["statpers"] <= target_t]
        if valid_t.empty:
            continue
        snap_t = valid_t.iloc[-1]  # most recent

        # snapshot_tm1: closest statpers to (fpedats - 91d)
        diffs = (grp["statpers"] - target_tm1).abs()
        snap_tm1 = grp.loc[diffs.idxmin()]

        rows.append({
            "ibes_ticker":      ticker,
            "fpedats":          fpedats,
            "eps_consensus_t":  snap_t["meanest"],
            "eps_consensus_tm1": snap_tm1["meanest"],
            "dispersion_t":     snap_t["stdev"],
            "n_analysts_t":     snap_t["numest"],
            "eps_actual":       snap_t["actual"],
            "anndats_act":      snap_t["anndats_act"],
        })

    return pd.DataFrame(rows)


def main():
    if OUT.exists():
        print(f"IBES consensus already exists ({OUT})")
        df = pd.read_parquet(OUT)
        print(f"  {len(df):,} rows, {df['ibes_ticker'].nunique():,} tickers")
        return

    print("Connecting to WRDS for IBES statsum_epsus...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        raw = pull_ibes_raw()

    print(f"Raw IBES rows: {len(raw):,}")
    print("Building consensus snapshots...")
    consensus = build_consensus_snapshots(raw)

    # Deduplicate: keep one row per (ticker, fpedats)
    consensus = consensus.drop_duplicates(subset=["ibes_ticker", "fpedats"])

    consensus.to_parquet(OUT, index=False)
    print(f"Saved {len(consensus):,} rows → {OUT}")
    print(f"  Tickers: {consensus['ibes_ticker'].nunique():,}")
    print(f"  fpedats range: {consensus['fpedats'].min()} – {consensus['fpedats'].max()}")


if __name__ == "__main__":
    main()
