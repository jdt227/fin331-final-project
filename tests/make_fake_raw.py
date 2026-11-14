"""
Make a small FAKE raw-data folder in the exact SEC / OpenFIGI / price formats, so the
whole pipeline can be tested in about a minute without internet.

    python tests/make_fake_raw.py crowd_test       (default: <system temp dir>/crowd_test)
    CROWD_DATA_DIR=crowd_test/data CROWD_OUTPUT_DIR=crowd_test/outputs \
        CROWD_UNIVERSE_SIZE=40 CROWD_CANDIDATE_POOL=60 python run_all.py --from 2

Built-in traps the pipeline must handle: late filers, amendments, notice filings,
duplicate originals, option and principal-amount rows, the 2023 $000s -> $ unit change,
an ETF in the top holdings, a 4:1 stock split, a ticker with no price data, a second
share class of the same issuer (CLSB), a stock with no holders in the first quarter
(NEWCO), a REIT (REITX, must be kept) and a stock with only a foreign listing (OLDCO,
must appear in universe_exclusions.csv).
"""
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(tempfile.gettempdir()) / "crowd_test")
import os
os.environ["CROWD_DATA_DIR"] = str(root / "data")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import config  # noqa: E402

rng = np.random.default_rng(331)
config.ensure_dirs()

# ---------------------------------------------------------------- securities
N_STOCKS, N_MGRS = 80, 400
SPECIAL = ["AAPL", "SPLT", "ETFX", "GONE", "CLSA", "CLSB", "NEWCO", "REITX", "OLDCO"]
tickers = SPECIAL + [f"S{i:03d}" for i in range(N_STOCKS - len(SPECIAL))]
cusips = ["037833100"] + [f"{rng.integers(10**5, 10**6)}{i % 10}10" for i in range(1, N_STOCKS)]
cusips = [c[:9].ljust(9, "0") for c in cusips]
cusips[5] = cusips[4][:6] + "305"          # CLSB: same issuer (first 6 digits) as CLSA
assert len(set(cusips)) == N_STOCKS
names = ["APPLE INC", "SPLITCO CORP", "FAKE ETF TRUST", "GONE CORP", "CLASSY CORP CL A",
         "CLASSY CORP CL C", "NEWCO INC", "REIT TRUST INC", "OLDCO INC"] + \
        [f"STOCK{i:03d} INC" for i in range(N_STOCKS - len(SPECIAL))]
popularity = rng.uniform(0.02, 0.6, N_STOCKS)
popularity[0], popularity[2] = 0.9, 0.85
popularity[4:9] = [0.7, 0.65, 0.8, 0.75, 0.8]     # make the traps big enough to matter

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
pd.DataFrame({"ticker": tickers + ["SPY"], "start": config.PRICE_START,
              "end": config.PRICE_END, "pulled_at_utc": "FAKE",
              "rows": [0 if t == "GONE" else len(dates) for t in tickers + ["SPY"]]}
             ).to_csv(config.PRICE_REQUESTS, index=False)
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
            if q == config.HOLDINGS_QUARTERS[0]:
                hold[tickers.index("NEWCO")] = False   # NEWCO is new after quarter 1
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
    typ2 = {"ETFX": "Mutual Fund", "REITX": "REIT"}.get(t, "Common Stock")
    exch = "GR" if t == "OLDCO" else "US"     # OLDCO: only a foreign listing today
    cache[c] = {"pulled_at_utc": "FAKE", "error": None, "data": [
        {"ticker": t, "name": n, "exchCode": exch, "securityType": "ETP" if t == "ETFX"
         else "Common Stock", "securityType2": typ2, "marketSector": "Equity"},
        {"ticker": t, "name": n, "exchCode": "UN" if exch == "US" else "GF",
         "securityType": "Common Stock", "securityType2": typ2, "marketSector": "Equity"}]}
config.FIGI_CACHE.write_text(json.dumps(cache))
print(f"Fake raw data written to {root / 'data'} ({len(needed)} SEC zips)")
