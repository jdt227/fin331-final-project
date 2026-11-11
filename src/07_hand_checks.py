"""
Step 7. Independent re-computation of one number from each pipeline step.

These checks deliberately do NOT reuse the pipeline's code: they go back to the raw
files with the simplest possible logic and compare. Any mismatch stops run_all.py.

Output: outputs/tables/hand_checks.csv
"""
import math
import os
import sys
import zipfile
import csv
import io

import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import config

d = pd.read_parquet(config.OUTPUTS / "final_dataset.parquet")
results = []


def record(step, what, pipeline, by_hand, tol=1e-9):
    ok = (pd.isna(pipeline) and pd.isna(by_hand)) or abs(pipeline - by_hand) <= tol
    results.append({"step": step, "check": what, "pipeline": pipeline, "by_hand": by_hand,
                    "match": bool(ok)})


# Pick a well-known stock in a middle quarter.
qmid = str(config.SIGNAL_QUARTERS[len(config.SIGNAL_QUARTERS) // 2])
cands = d[(d["quarter"] == qmid) & d["ret_fwd"].notna()]
row = cands[cands["ticker"] == "AAPL"]
row = (row if len(row) else cands.head(1)).iloc[0]
cusip, ticker, q = row["cusip"], row["ticker"], pd.Period(qmid, freq="Q")
qend = q.end_time.normalize()
deadline = qend + pd.Timedelta(days=45)
print(f"Hand-checking {ticker} ({cusip}) in {qmid}")

# ---- Check A (steps 1-3): number of 13F holders, straight from the raw zips.
best = {}   # cik -> (filing_date, accession) of the last on-time original 13F-HR
holders_by_acc = {}
for name in config.sec_files_needed():
    with zipfile.ZipFile(config.RAW_13F / name) as zf:
        names = {n.split("/")[-1].upper(): n for n in zf.namelist()}
        cover = {}
        with zf.open(names["COVERPAGE.TSV"]) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8"), delimiter="\t"):
                cover[r["ACCESSION_NUMBER"]] = r["REPORTTYPE"].strip().upper()
        with zf.open(names["SUBMISSION.TSV"]) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8"), delimiter="\t"):
                if r["SUBMISSIONTYPE"].strip() != "13F-HR":
                    continue
                if cover.get(r["ACCESSION_NUMBER"]) not in ("13F HOLDINGS REPORT",
                                                             "13F COMBINATION REPORT"):
                    continue
                per = pd.to_datetime(r["PERIODOFREPORT"].title(), format="%d-%b-%Y")
                fd = pd.to_datetime(r["FILING_DATE"].title(), format="%d-%b-%Y")
                if per != qend or fd > deadline:
                    continue
                cik = int(r["CIK"])
                key = (fd, r["ACCESSION_NUMBER"])
                if cik not in best or key > best[cik]:
                    best[cik] = key
        with zf.open(names["INFOTABLE.TSV"]) as f:
            for r in csv.DictReader(io.TextIOWrapper(f, "utf-8"), delimiter="\t"):
                if r["CUSIP"].strip().upper() != cusip:
                    continue
                if r["SSHPRNAMTTYPE"].strip().upper() != "SH" or r["PUTCALL"].strip():
                    continue
                if float(r["SSHPRNAMT"] or 0) <= 0:
                    continue
                holders_by_acc[r["ACCESSION_NUMBER"]] = True
final_accs = {acc for _, acc in best.values()}
n_hand = sum(1 for a in holders_by_acc if a in final_accs)
record("1-3 parse/stats", f"n_holders {ticker} {qmid}", float(row["n_holders"]), float(n_hand))

# ---- Check B (step 4-5): forward return from the raw price file.
p = pd.read_parquet(config.PRICES)
p = p[p["ticker"] == ticker].set_index("date")["adj_close"].sort_index()
p0 = p[p.index <= row["formation_date"]].iloc[-1]
p1 = p[p.index <= row["holding_end_date"]].iloc[-1]
record("4-5 returns", f"ret_fwd {ticker} {qmid}", float(row["ret_fwd"]), p1 / p0 - 1, 1e-12)

# ---- Check C (step 5): formation date is the first trading day after the deadline.
spy = pd.read_parquet(config.PRICES).query("ticker == @config.MARKET_TICKER")["date"]
first_after = spy[spy > deadline].min()
record("5 timing", f"formation_date {qmid} (days since 1970)",
       row["formation_date"].value / 8.64e13, first_after.value / 8.64e13)

# ---- Check D (step 6): Q5-Q1 for the primary signal in one quarter, by plain sorting.
sig = config.PRIMARY_SIGNAL
g = d[(d["quarter"] == qmid)].dropna(subset=[sig, "exret_fwd"])
pairs = list(zip(g[sig], range(len(g)), g["exret_fwd"]))   # ties broken by row order
pairs.sort()
n = len(pairs)
bins = {i: [] for i in range(1, 6)}
for rank, (_, _, r) in enumerate(pairs, start=1):
    bins[math.ceil(rank * 5 / n)].append(r)
ls_hand = sum(bins[5]) / len(bins[5]) - sum(bins[1]) / len(bins[1])
ls_pipe = pd.read_csv(config.TABLES / "long_short_by_quarter.csv").query(
    "signal == @sig and quarter == @qmid")["long_short"].iloc[0]
record("6 analysis", f"Q5-Q1 {sig} {qmid}", float(ls_pipe), ls_hand, 1e-12)

out = pd.DataFrame(results)
out.to_csv(config.TABLES / "hand_checks.csv", index=False)
print(out.to_string(index=False))
if not out["match"].all():
    sys.exit("HAND CHECK FAILED - see outputs/tables/hand_checks.csv")
print("All hand checks match.")
