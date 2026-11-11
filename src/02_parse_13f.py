"""
Step 2. Parse the SEC zips into a clean manager x stock x quarter holdings panel.

Input : data/raw/sec_13f/*.zip
Output: data/interim/filings.parquet            one row per kept 13F filing (CIK x quarter)
        data/interim/holdings/<quarter>.parquet  one row per CIK x CUSIP x quarter
        outputs/tables/filing_filter_counts.csv  how many filings each rule removed

Point-in-time rules (the auditors' #1 target is look-ahead):
  * keep only ORIGINAL 13F-HR filings (amendments arrive later and were not public at
    the signal date);
  * keep only filings made on or before quarter end + 45 days (the formation date
    uses exactly this information set);
  * if a manager filed more than one original for a quarter by the deadline, keep the
    last one filed by the deadline.
Holding rules: shares only (SSHPRNAMTTYPE == 'SH'), no option positions (PUTCALL blank).
VALUE is converted to dollars (filings before 2023-01-03 report $000s).
"""
import os
import sys
import zipfile

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import zip_member, parse_sec_date, qstr

config.ensure_dirs()
(config.INTERIM / "holdings").mkdir(exist_ok=True)
parts_dir = config.INTERIM / "holdings_parts"
parts_dir.mkdir(exist_ok=True)

KEEP_REPORT_TYPES = {"13F HOLDINGS REPORT", "13F COMBINATION REPORT"}
needed_quarters = set(config.HOLDINGS_QUARTERS)
files = [config.RAW_13F / f for f in config.sec_files_needed()]
missing = [f.name for f in files if not f.exists()]
if missing:
    sys.exit(f"Missing raw files (run 01_download_13f.py): {missing}")

# ---------------------------------------------------------------- 1. filings
counts = []
filings = []
for path in files:
    with zipfile.ZipFile(path) as zf:
        sub = pd.read_csv(zf.open(zip_member(zf, "SUBMISSION")), sep="\t", dtype=str)
        cov = pd.read_csv(zf.open(zip_member(zf, "COVERPAGE")), sep="\t", dtype=str,
                          usecols=["ACCESSION_NUMBER", "REPORTTYPE", "FILINGMANAGER_NAME"])
    f = sub.merge(cov, on="ACCESSION_NUMBER", how="left", validate="1:1")
    f["filing_date"] = parse_sec_date(f["FILING_DATE"])
    f["period_date"] = parse_sec_date(f["PERIODOFREPORT"])
    c = {"file": path.name, "all_submissions": len(f)}

    f = f[f["SUBMISSIONTYPE"].str.strip() == "13F-HR"]
    c["original_13F_HR"] = len(f)
    f = f[f["REPORTTYPE"].str.strip().str.upper().isin(KEEP_REPORT_TYPES)]
    c["holdings_or_combination"] = len(f)
    f = f[f["period_date"].notna() & f["period_date"].dt.is_quarter_end]
    f["quarter"] = f["period_date"].dt.to_period("Q")
    f = f[f["quarter"].isin(needed_quarters)]
    c["in_sample_quarters"] = len(f)
    deadline = f["quarter"].apply(config.filing_deadline)
    c["late_dropped"] = int((f["filing_date"] > deadline).sum())
    f = f[f["filing_date"] <= deadline]
    c["kept"] = len(f)
    counts.append(c)
    filings.append(f[["ACCESSION_NUMBER", "CIK", "FILINGMANAGER_NAME", "quarter",
                      "filing_date"]].assign(source_file=path.name))
    print(f"  {path.name}: kept {c['kept']:,} of {c['all_submissions']:,} submissions")

filings = pd.concat(filings, ignore_index=True)
filings["CIK"] = filings["CIK"].str.strip().astype("int64")
n_before = len(filings)
filings = (filings.sort_values(["CIK", "quarter", "filing_date", "ACCESSION_NUMBER"])
                  .drop_duplicates(["CIK", "quarter"], keep="last"))
counts.append({"file": "ALL", "duplicate_originals_dropped": n_before - len(filings),
               "kept": len(filings)})
assert not filings.duplicated(["CIK", "quarter"]).any()
assert not filings.duplicated("ACCESSION_NUMBER").any()
filings.columns = ["accession", "cik", "manager_name", "quarter", "filing_date", "source_file"]
filings["quarter"] = filings["quarter"].astype(str)
filings.to_parquet(config.INTERIM / "filings.parquet", index=False)
pd.DataFrame(counts).to_csv(config.TABLES / "filing_filter_counts.csv", index=False)
print(f"Kept {len(filings):,} manager-quarter filings.")
print(filings.groupby("quarter").size().rename("managers").to_string())

# ---------------------------------------------------------------- 2. holdings
acc = filings.set_index("accession")[["cik", "quarter", "filing_date"]]
info_cols = ["ACCESSION_NUMBER", "NAMEOFISSUER", "TITLEOFCLASS", "CUSIP", "VALUE",
             "SSHPRNAMT", "SSHPRNAMTTYPE", "PUTCALL"]

for path in files:
    pieces = []
    with zipfile.ZipFile(path) as zf:
        reader = pd.read_csv(zf.open(zip_member(zf, "INFOTABLE")), sep="\t", dtype=str,
                             usecols=info_cols, chunksize=1_000_000)
        for ch in reader:
            ch = ch[ch["ACCESSION_NUMBER"].isin(acc.index)]
            ch = ch[ch["SSHPRNAMTTYPE"].str.strip().str.upper() == "SH"]
            ch = ch[ch["PUTCALL"].isna() | (ch["PUTCALL"].str.strip() == "")]
            ch["CUSIP"] = ch["CUSIP"].str.strip().str.upper()
            ch = ch[ch["CUSIP"].str.len() == 9]
            ch["value"] = pd.to_numeric(ch["VALUE"], errors="coerce")
            ch["shares"] = pd.to_numeric(ch["SSHPRNAMT"], errors="coerce")
            ch = ch[(ch["shares"] > 0) & ch["value"].notna()]
            pieces.append(ch[["ACCESSION_NUMBER", "CUSIP", "NAMEOFISSUER", "TITLEOFCLASS",
                              "value", "shares"]])
    if not pieces:
        continue
    h = pd.concat(pieces, ignore_index=True)
    h = h.join(acc, on="ACCESSION_NUMBER", validate="m:1")
    # VALUE unit change: $000s before 2023-01-03, dollars after.
    h.loc[h["filing_date"] < config.VALUE_IN_DOLLARS_FROM, "value"] *= 1000
    # One manager can list the same stock on several lines (different discretion /
    # other-manager codes). Sum to one row per manager x stock x quarter.
    h = (h.groupby(["quarter", "cik", "CUSIP"], as_index=False)
           .agg(shares=("shares", "sum"), value=("value", "sum"),
                issuer=("NAMEOFISSUER", "first"), title=("TITLEOFCLASS", "first")))
    h.to_parquet(parts_dir / (path.stem + ".parquet"), index=False)
    print(f"  {path.name}: {len(h):,} manager-stock rows")

# A given filing lives in exactly one zip, so concatenating parts by quarter is safe.
parts = sorted(parts_dir.glob("*.parquet"))
for q in config.HOLDINGS_QUARTERS:
    qh = pd.concat([pd.read_parquet(p, filters=[("quarter", "==", str(q))]) for p in parts],
                   ignore_index=True)
    qh = qh.rename(columns={"CUSIP": "cusip"})
    assert not qh.duplicated(["cik", "cusip"]).any(), f"duplicate manager-stock rows in {q}"
    qh.to_parquet(config.INTERIM / "holdings" / f"{qstr(q)}.parquet", index=False)
    print(f"  {q}: {len(qh):,} rows, {qh['cik'].nunique():,} managers, "
          f"{qh['cusip'].nunique():,} CUSIPs")
print("Done.")
