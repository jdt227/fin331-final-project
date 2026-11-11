"""
Step 3. Stock-level 13F statistics, CUSIP -> ticker mapping, and the stock universe.

Input : data/interim/holdings/<quarter>.parquet
Output: data/interim/cusip_quarter_stats.parquet  every CUSIP x quarter: holders, $ held
        data/raw/openfigi_cache.json              raw OpenFIGI answers (cached, re-usable)
        data/raw/cusip_ticker_map.csv             parsed map: cusip -> ticker, type
        data/interim/universe.parquet             top-N common stocks per signal quarter
        outputs/tables/cusip_mapping_report.csv   mapping coverage + name-mismatch checks

Universe rule (point in time, no survivorship from today's index lists):
  rank stocks each quarter by 13F-reported institutional dollar holdings, computed as
  (total 13F shares) x (median price implied by filers' value/shares). The median makes
  the ranking robust to a few filers who mis-report the $000s vs $ units. Keep US common
  stocks (OpenFIGI securityType2 == 'Common Stock', exchCode == 'US'), top UNIVERSE_SIZE.
"""
import json
import os
import re
import sys
import time

import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(__file__))
import config
from common import log_provenance, utc_now, yf_ticker, qstr

config.ensure_dirs()

# ---------------------------------------------------------------- 1. CUSIP x quarter stats
stats = []
for q in config.HOLDINGS_QUARTERS:
    h = pd.read_parquet(config.INTERIM / "holdings" / f"{qstr(q)}.parquet")
    h["implied_px"] = h["value"] / h["shares"]
    s = (h.groupby("cusip")
           .agg(n_holders=("cik", "nunique"), inst_shares=("shares", "sum"),
                median_px=("implied_px", "median"), issuer=("issuer", "first"),
                title=("title", "first"))
           .reset_index())
    s["inst_dollar"] = s["inst_shares"] * s["median_px"]
    s["quarter"] = qstr(q)
    s["n_filers_total"] = h["cik"].nunique()
    stats.append(s)
stats = pd.concat(stats, ignore_index=True)
assert not stats.duplicated(["cusip", "quarter"]).any()
stats.to_parquet(config.INTERIM / "cusip_quarter_stats.parquet", index=False)

# ---------------------------------------------------------------- 2. candidate CUSIPs
sig_q = [qstr(q) for q in config.SIGNAL_QUARTERS]
cand = (stats[stats["quarter"].isin(sig_q)]
        .sort_values(["quarter", "inst_dollar"], ascending=[True, False])
        .groupby("quarter").head(config.CANDIDATE_POOL))
cusips = sorted(cand["cusip"].unique())
print(f"{len(cusips):,} candidate CUSIPs to map")

# ---------------------------------------------------------------- 3. OpenFIGI mapping
cache = json.loads(config.FIGI_CACHE.read_text()) if config.FIGI_CACHE.exists() else {}
todo = [c for c in cusips if c not in cache]
if todo:
    key = os.environ.get("OPENFIGI_API_KEY")
    batch, pause = (100, 0.25) if key else (10, 2.5)   # OpenFIGI public rate limits
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-OPENFIGI-APIKEY"] = key
    print(f"Querying OpenFIGI for {len(todo):,} CUSIPs ({'with' if key else 'without'} API key)")
    for i in range(0, len(todo), batch):
        chunk = todo[i:i + batch]
        jobs = [{"idType": "ID_CUSIP", "idValue": c} for c in chunk]
        for attempt in range(5):
            r = requests.post("https://api.openfigi.com/v3/mapping", json=jobs,
                              headers=headers, timeout=60)
            if r.status_code == 429:
                time.sleep(30)
                continue
            r.raise_for_status()
            break
        for c, res in zip(chunk, r.json()):
            cache[c] = {"pulled_at_utc": utc_now(), "data": res.get("data", []),
                        "error": res.get("error") or res.get("warning")}
        config.FIGI_CACHE.write_text(json.dumps(cache))
        time.sleep(pause)
    log_provenance("openfigi_cache.json", "https://api.openfigi.com/v3/mapping (ID_CUSIP)",
                   config.FIGI_CACHE, note=f"{len(cache)} CUSIPs cached")


def pick(rows):
    """Prefer the US composite listing of a common stock."""
    us = [r for r in rows if r.get("exchCode") == "US"]
    common = [r for r in us if r.get("securityType2") == "Common Stock"]
    return (common or us or rows or [None])[0]


recs = []
for c in cusips:
    rows = cache.get(c, {}).get("data", [])
    best = pick(rows)
    recs.append({
        "cusip": c,
        "figi_ticker": best.get("ticker") if best else None,
        "figi_name": best.get("name") if best else None,
        "security_type": best.get("securityType") if best else None,
        "security_type2": best.get("securityType2") if best else None,
        "exch_code": best.get("exchCode") if best else None,
        "n_figi_results": len(rows),
    })
cmap = pd.DataFrame(recs)
cmap["ticker"] = cmap["figi_ticker"].dropna().map(yf_ticker)
cmap.to_csv(config.CUSIP_MAP, index=False)

# ---------------------------------------------------------------- 4. universe
u = cand.merge(cmap, on="cusip", how="left", validate="m:1")
u["is_common_us"] = (u["security_type2"] == "Common Stock") & (u["exch_code"] == "US") \
    & u["ticker"].notna()
u = u[u["is_common_us"]]
# Two CUSIPs can map to one ticker (e.g. after a CUSIP change). Keep the larger one.
u = (u.sort_values(["quarter", "inst_dollar"], ascending=[True, False])
      .drop_duplicates(["quarter", "ticker"]))
u = u.groupby("quarter").head(config.UNIVERSE_SIZE).copy()
u["size_rank"] = u.groupby("quarter")["inst_dollar"].rank(ascending=False, method="first")
universe = u[["quarter", "cusip", "ticker", "issuer", "figi_name", "inst_dollar",
              "size_rank"]].reset_index(drop=True)
assert not universe.duplicated(["quarter", "cusip"]).any()
assert not universe.duplicated(["quarter", "ticker"]).any()
universe.to_parquet(config.INTERIM / "universe.parquet", index=False)


# ---------------------------------------------------------------- 5. mapping checks
def first_word(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper()).split()
    return s[0] if s else ""


universe["name_match"] = [first_word(a) == first_word(b)
                          for a, b in zip(universe["issuer"], universe["figi_name"])]
report = pd.DataFrame([
    {"check": "candidate CUSIPs", "value": len(cusips)},
    {"check": "CUSIPs with any OpenFIGI result", "value": int((cmap["n_figi_results"] > 0).sum())},
    {"check": "CUSIPs mapped to US common stock", "value": int(((cmap["security_type2"] == "Common Stock") & (cmap["exch_code"] == "US")).sum())},
    {"check": "universe stock-quarters", "value": len(universe)},
    {"check": "universe quarters with < UNIVERSE_SIZE stocks", "value": int((universe.groupby("quarter").size() < config.UNIVERSE_SIZE).sum())},
    {"check": "universe rows where 13F name first word != OpenFIGI name first word", "value": int((~universe["name_match"]).sum())},
])
report.to_csv(config.TABLES / "cusip_mapping_report.csv", index=False)
(universe[~universe["name_match"]]
 .drop_duplicates("cusip")[["cusip", "ticker", "issuer", "figi_name"]]
 .to_csv(config.TABLES / "cusip_name_mismatches.csv", index=False))
print(report.to_string(index=False))
print("Name mismatches to eyeball: outputs/tables/cusip_name_mismatches.csv")
print("Done.")
