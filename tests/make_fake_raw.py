"""
Make a small FAKE raw-data folder in the exact SEC / OpenFIGI / price formats, so the
whole pipeline can be tested in about a minute without internet.

    python tests/make_fake_raw.py /tmp/crowd_test
    CROWD_DATA_DIR=/tmp/crowd_test/data CROWD_OUTPUT_DIR=/tmp/crowd_test/outputs \
        CROWD_UNIVERSE_SIZE=40 CROWD_CANDIDATE_POOL=60 python run_all.py

Built-in traps the pipeline must handle: late filers, amendments, notice filings,
duplicate originals, option and principal-amount rows, the 2023 $000s -> $ unit change,
an ETF in the top holdings, a 4:1 stock split, and a ticker with no price data.
"""
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/crowd_test")
import os
os.environ["CROWD_DATA_DIR"] = str(root / "data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import config  # noqa: E402

rng = np.random.default_rng(331)
config.ensure_dirs()

# ---------------------------------------------------------------- securities
N_STOCKS, N_MGRS = 80, 400
tickers = ["AAPL", "SPLT", "ETFX", "GONE"] + [f"S{i:03d}" for i in range(N_STOCKS - 4)]
cusips = ["037833100"] + [f"{rng.integers(10**5, 10**6)}{i % 10}10" for i in range(1, N_STOCKS)]
cusips = [c[:9].ljust(9, "0") for c in cusips]
assert len(set(cusips)) == N_STOCKS
names = ["APPLE INC", "SPLITCO CORP", "FAKE ETF TRUST", "GONE CORP"] + \
        [f"STOCK{i:03d} INC" for i in range(N_STOCKS - 4)]
popularity = rng.uniform(0.02, 0.6, N_STOCKS)
popularity[0], popularity[2] = 0.9, 0.85

# ---------------------------------------------------------------- prices
dates = pd.bdate_range(config.PRICE_START, config.PRICE_END)
split_date = dates[len(dates) // 2]
rets = rng.normal(0.0003, 0.015, (len(dates), N_STOCKS))
level = 50 * np.exp(np.cumsum(rets, axis=0))     # adjusted prices (continuous)
mkt = 400 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, len(dates))))
rows = []
for j, t in enumerate(tickers):
    if t == "GONE":
        continue   # simulates a delisted ticker Yahoo no longer serves
    sr = np.where((dates == split_date) & (t == "SPLT"), 4.0, 0.0)
    rows.append(pd.DataFrame({"date": dates, "ticker": t, "adj_close": level[:, j],
                              "split_ratio": sr}))
rows.append(pd.DataFrame({"date": dates, "ticker": "SPY", "adj_close": mkt, "split_ratio": 0.0}))
pd.concat(rows).to_parquet(config.PRICES, index=False)
(config.RAW / "prices_tried_empty.txt").write_text("GONE")
px = pd.DataFrame(level, index=dates, columns=tickers)


def raw_price(t, d):
    """Unadjusted price: before the split SPLT traded at 4x its adjusted price."""
    p = px[t].asof(d)
    return p * 4 if (t == "SPLT" and d < split_date) else p


# ---------------------------------------------------------------- filings
fmt = lambda d: d.strftime("%d-%b-%Y").upper()
windows = {n: (pd.Timestamp(a), pd.Timestamp(b)) for n, a, b in config.SEC_FILES}
needed = config.sec_files_needed()
tables = {n: {"SUBMISSION": [], "COVERPAGE": [], "INFOTABLE": []} for n in needed}
acc_id, sk = 0, 0
ciks = rng.choice(np.arange(1_000_000, 2_000_000), N_MGRS, replace=False)

for q in config.HOLDINGS_QUARTERS:
    qend = config.quarter_end(q)
    for m, cik in enumerate(ciks):
        if rng.random() < 0.05:            # some managers skip a quarter (entry / exit)
            continue
        n_files = 2 if rng.random() < 0.03 else 1
        for k in range(n_files):
            lag = int(rng.integers(5, 44)) if rng.random() > 0.06 else int(rng.integers(46, 80))
            fdate = qend + pd.Timedelta(days=lag + k)
            zipname = next((n for n in needed if windows[n][0] <= fdate <= windows[n][1]), None)
            if zipname is None:
                continue
            acc_id += 1
            acc = f"0000{acc_id:06d}-{q.year % 100:02d}-{acc_id:06d}"
            stype = "13F-HR"
            r = rng.random()
            if r < 0.03:
                stype = "13F-HR/A"
            rtype = "13F NOTICE REPORT" if r > 0.98 else "13F HOLDINGS REPORT"
            T = tables[zipname]
            T["SUBMISSION"].append({"ACCESSION_NUMBER": acc, "FILING_DATE": fmt(fdate),
                                    "SUBMISSIONTYPE": stype, "CIK": str(cik).zfill(10),
                                    "PERIODOFREPORT": fmt(qend)})
            T["COVERPAGE"].append({"ACCESSION_NUMBER": acc, "REPORTCALENDARORQUARTER": fmt(qend),
                                   "ISAMENDMENT": "Y" if stype.endswith("/A") else "N",
                                   "REPORTTYPE": rtype, "FILINGMANAGER_NAME": f"MANAGER {m}"})
            if rtype == "13F NOTICE REPORT":
                continue
            drift = 0.15 * np.sin(q.ordinal / 2 + np.arange(N_STOCKS))
            hold = rng.random(N_STOCKS) < np.clip(popularity + drift, 0.01, 0.97)
            for j in np.where(hold)[0]:
                sh = int(rng.integers(1_000, 500_000))
                if tickers[j] == "SPLT" and qend >= split_date:
                    sh *= 4
                val = sh * raw_price(tickers[j], qend)
                if fdate < config.VALUE_IN_DOLLARS_FROM:
                    val /= 1000
                sk += 1
                base = {"ACCESSION_NUMBER": acc, "INFOTABLE_SK": sk,
                        "NAMEOFISSUER": names[j], "TITLEOFCLASS": "COM", "CUSIP": cusips[j],
                        "FIGI": "", "VALUE": int(round(val)), "SSHPRNAMT": sh,
                        "SSHPRNAMTTYPE": "SH", "PUTCALL": "", "INVESTMENTDISCRETION": "SOLE",
                        "OTHERMANAGER": "", "VOTING_AUTH_SOLE": sh, "VOTING_AUTH_SHARED": 0,
                        "VOTING_AUTH_NONE": 0}
                T["INFOTABLE"].append(base)
                if rng.random() < 0.02:     # option position: must be ignored
                    sk += 1
                    T["INFOTABLE"].append({**base, "INFOTABLE_SK": sk, "PUTCALL": "Call"})
                if rng.random() < 0.02:     # second line, same stock: must be summed
                    sk += 1
                    T["INFOTABLE"].append({**base, "INFOTABLE_SK": sk,
                                           "INVESTMENTDISCRETION": "DFND"})

for name, T in tables.items():
    with zipfile.ZipFile(config.RAW_13F / name, "w", zipfile.ZIP_DEFLATED) as zf:
        for tbl, recs in T.items():
            zf.writestr(f"{tbl}.tsv", pd.DataFrame(recs).to_csv(sep="\t", index=False))

# ---------------------------------------------------------------- OpenFIGI cache
cache = {}
for c, t, n in zip(cusips, tickers, names):
    typ2 = "Mutual Fund" if t == "ETFX" else "Common Stock"
    cache[c] = {"pulled_at_utc": "FAKE", "error": None, "data": [
        {"ticker": t, "name": n, "exchCode": "US", "securityType": "ETP" if t == "ETFX"
         else "Common Stock", "securityType2": typ2, "marketSector": "Equity"},
        {"ticker": t, "name": n, "exchCode": "UN", "securityType": "Common Stock",
         "securityType2": typ2, "marketSector": "Equity"}]}
config.FIGI_CACHE.write_text(json.dumps(cache))
print(f"Fake raw data written to {root / 'data'} ({len(needed)} SEC zips)")
