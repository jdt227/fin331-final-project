"""
Step 3. Stock-level 13F statistics, CUSIP -> ticker mapping, and the stock universe.

Input : data/interim/holdings/<quarter>.parquet
Output: data/interim/cusip_quarter_stats.parquet  every CUSIP x quarter: holders, $ held
        data/raw/openfigi_cache.json              raw OpenFIGI answers (cached, re-usable)
        data/raw/cusip_ticker_map.csv             parsed map: cusip -> ticker, type
        data/interim/universe.parquet             top-N common stocks per signal quarter
        outputs/tables/cusip_mapping_report.csv   mapping coverage + name-mismatch checks
        outputs/tables/universe_exclusions.csv    every candidate left out, and why

Universe rule (point in time, no survivorship from today's index lists):
  rank stocks each quarter by 13F-reported institutional dollar holdings, computed as
  (total 13F shares) x (median price implied by filers' value/shares). The median makes
  the ranking robust to a few filers who mis-report the $000s vs $ units. Keep US common
  equity (OpenFIGI securityType2 in config.COMMON_TYPES, i.e. common stock or REIT, with
  a U.S. listing), one share class per issuer, top UNIVERSE_SIZE.

Survivorship guard: OpenFIGI describes securities as they are TODAY. A firm acquired after
our sample (Activision, Pioneer), a CUSIP that changed later, or a foreign-incorporated
firm with a CINS code (Linde, Accenture) may have no current U.S. listing. Such stocks
were real, investable U.S. stocks at the time, so dropping them would bias the sample
toward survivors. We (1) retry CINS codes with idType ID_CINS, and (2) apply the
hand-reviewed map in data/manual_ticker_map.csv. Every candidate still excluded is listed,
with its reason, in outputs/tables/universe_exclusions.csv for review.
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
from common import log_provenance, safe_write_text, utc_now, yf_ticker, qstr

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
cache = json.loads(config.FIGI_CACHE.read_text(encoding="utf-8")) if config.FIGI_CACHE.exists() else {}


def query_openfigi(ids, id_type):
    """Map identifiers with OpenFIGI; store each raw answer in the cache."""
    key = os.environ.get("OPENFIGI_API_KEY")
    batch, pause = (100, 0.25) if key else (10, 2.5)   # OpenFIGI public rate limits
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-OPENFIGI-APIKEY"] = key
    print(f"Querying OpenFIGI ({id_type}) for {len(ids):,} ids ({'with' if key else 'without'} API key)")
    for i in range(0, len(ids), batch):
        chunk = ids[i:i + batch]
        jobs = [{"idType": id_type, "idValue": c} for c in chunk]
        for attempt in range(5):
            r = requests.post("https://api.openfigi.com/v3/mapping", json=jobs,
                              headers=headers, timeout=60)
            if r.status_code == 429:
                time.sleep(30)
                continue
            r.raise_for_status()
            break
        for c, res in zip(chunk, r.json()):
            entry = {"pulled_at_utc": utc_now(), "data": res.get("data", []),
                     "error": res.get("error") or res.get("warning")}
            if id_type == "ID_CUSIP":
                cache[c] = entry
            else:   # keep the original CUSIP answer; add the CINS answer beside it
                cache[c]["cins"] = entry
        if (i // batch) % 10 == 9 or i + batch >= len(ids):   # save every 10 batches
            safe_write_text(config.FIGI_CACHE, json.dumps(cache))
        time.sleep(pause)


todo = [c for c in cusips if c not in cache]
if todo:
    query_openfigi(todo, "ID_CUSIP")
# CINS codes (foreign issuers; first character is a letter) often only map as ID_CINS.
cins_todo = [c for c in cusips if c[0].isalpha() and not cache[c]["data"]
             and "cins" not in cache[c]]
if cins_todo:
    query_openfigi(cins_todo, "ID_CINS")
if todo or cins_todo:
    log_provenance("openfigi_cache.json", "https://api.openfigi.com/v3/mapping "
                   "(ID_CUSIP; ID_CINS retry for unmatched CINS codes)",
                   config.FIGI_CACHE, note=f"{len(cache)} CUSIPs cached")


def pick(rows):
    """Prefer the US composite listing of common equity."""
    us = [r for r in rows if r.get("exchCode") == "US"]
    common = [r for r in us if r.get("securityType2") in config.COMMON_TYPES]
    return (common or us or rows or [None])[0]


manual = pd.read_csv(config.MANUAL_MAP, dtype=str) if config.MANUAL_MAP.exists() else \
    pd.DataFrame(columns=["cusip", "ticker", "include", "issuer", "reason", "source"])
assert manual["include"].isin(["yes", "no"]).all(), "manual map: include must be yes/no"
assert manual.loc[manual["include"] == "yes", "ticker"].notna().all(), "manual map: ticker missing"
assert not manual.duplicated("cusip").any(), "duplicate CUSIP in manual_ticker_map.csv"
manual = manual.set_index("cusip")

recs = []
for c in cusips:
    entry = cache.get(c, {})
    rows = entry.get("data", []) or entry.get("cins", {}).get("data", [])
    best = pick(rows)
    rec = {
        "cusip": c,
        "figi_ticker": best.get("ticker") if best else None,
        "figi_name": best.get("name") if best else None,
        "security_type": best.get("securityType") if best else None,
        "security_type2": best.get("securityType2") if best else None,
        "exch_code": best.get("exchCode") if best else None,
        "n_figi_results": len(rows),
        "map_source": "openfigi_cins" if (rows and not entry.get("data")) else "openfigi",
    }
    if c in manual.index and manual.at[c, "include"] == "yes":
        # hand-reviewed override (see data/manual_ticker_map.csv)
        rec.update({"figi_ticker": manual.at[c, "ticker"],
                    "figi_name": rec["figi_name"] or manual.at[c, "issuer"],
                    "security_type2": "Common Stock", "exch_code": "US",
                    "map_source": "manual"})
    elif c in manual.index:   # reviewed by hand and deliberately left out
        rec.update({"security_type2": "Excluded by hand review: " + manual.at[c, "reason"],
                    "map_source": "manual"})
    recs.append(rec)
cmap = pd.DataFrame(recs)
cmap["ticker"] = cmap["figi_ticker"].dropna().map(yf_ticker)
cmap.to_csv(config.CUSIP_MAP, index=False)

# ---------------------------------------------------------------- 4. universe
u = cand.merge(cmap, on="cusip", how="left", validate="m:1")


def reason(r):
    if str(r["security_type2"]).startswith("Excluded by hand review"):
        return r["security_type2"]
    if r["n_figi_results"] == 0 and r["map_source"] != "manual":
        return "no OpenFIGI match"
    if r["security_type2"] == "Mutual Fund":
        return "fund / ETF"
    if r["security_type2"] == "Depositary Receipt":
        return "ADR / depositary receipt (foreign issuer)"
    if r["security_type2"] not in config.COMMON_TYPES:
        return f"not common equity ({r['security_type2']})"
    if r["exch_code"] != "US":
        return "no current U.S. listing (likely acquired or CUSIP changed)"
    if pd.isna(r["ticker"]):
        return "no ticker"
    return ""


u["excl_reason"] = u.apply(reason, axis=1)
excluded = [u[u["excl_reason"] != ""]]
u = u[u["excl_reason"] == ""].copy()
# Two CUSIPs can map to one ticker (e.g. after a CUSIP change). Keep the larger one.
u = u.sort_values(["quarter", "inst_dollar"], ascending=[True, False])
dup = u.duplicated(["quarter", "ticker"])
excluded.append(u[dup].assign(excl_reason="same ticker as a larger CUSIP"))
u = u[~dup]
# One share class per issuer (GOOG/GOOGL, BRK-A/BRK-B): the first 6 CUSIP characters
# identify the issuer. Keep the class held by the MOST 13F managers (the class
# institutions actually trade). Dollar holdings are noisy for high-priced classes such as
# BRK-A and made the chosen class flip between quarters.
u["issuer_id"] = u["cusip"].str[:6]
u = u.sort_values(["quarter", "n_holders", "inst_dollar"], ascending=[True, False, False])
dup = u.duplicated(["quarter", "issuer_id"])
excluded.append(u[dup].assign(excl_reason="second share class of the same issuer"))
u = u[~dup]
u = u.sort_values(["quarter", "inst_dollar"], ascending=[True, False])
excluded.append(u.groupby("quarter").cumcount().ge(config.UNIVERSE_SIZE)
                .pipe(lambda m: u[m]).assign(excl_reason="below the top-N size cutoff"))
u = u.groupby("quarter").head(config.UNIVERSE_SIZE).copy()
u["size_rank"] = u.groupby("quarter")["inst_dollar"].rank(ascending=False, method="first")
universe = u[["quarter", "cusip", "ticker", "issuer", "figi_name", "map_source",
              "inst_dollar", "size_rank"]].reset_index(drop=True)
assert not universe.duplicated(["quarter", "cusip"]).any()
assert not universe.duplicated(["quarter", "ticker"]).any()
assert not u.duplicated(["quarter", "issuer_id"]).any()
universe.to_parquet(config.INTERIM / "universe.parquet", index=False)

# Every candidate that was big enough to be considered but left out, and why. Candidates
# excluded only for size are not listed. A stock-quarter whose inst_dollar beats the
# smallest universe member that quarter would have been IN the universe if mapped.
cut = universe.groupby("quarter")["inst_dollar"].min().rename("cutoff")
ex = pd.concat(excluded, ignore_index=True).join(cut, on="quarter")
ex = ex[ex["excl_reason"] != "below the top-N size cutoff"]
ex["would_be_in_top_n"] = ex["inst_dollar"] >= ex["cutoff"]
ex = (ex.sort_values("inst_dollar", ascending=False)
        .groupby("cusip", as_index=False)
        .agg(issuer=("issuer", "first"), figi_ticker=("figi_ticker", "first"),
             security_type2=("security_type2", "first"), exch_code=("exch_code", "first"),
             reason=("excl_reason", "first"), quarters=("quarter", "nunique"),
             quarters_in_top_n=("would_be_in_top_n", "sum"),
             max_inst_dollar=("inst_dollar", "max"))
        .sort_values("max_inst_dollar", ascending=False))
ex.to_csv(config.TABLES / "universe_exclusions.csv", index=False)


# ---------------------------------------------------------------- 5. mapping checks
def first_word(s):
    s = re.sub(r"[^A-Z0-9 ]", " ", str(s).upper()).split()
    return s[0] if s else ""


universe["name_match"] = [first_word(a) == first_word(b)
                          for a, b in zip(universe["issuer"], universe["figi_name"])]
is_common = cmap["security_type2"].isin(config.COMMON_TYPES) & (cmap["exch_code"] == "US")
review = ex["reason"].str.startswith(("no OpenFIGI", "no current U.S.", "no ticker"))
report = pd.DataFrame([
    {"check": "candidate CUSIPs", "value": len(cusips)},
    {"check": "CUSIPs with any OpenFIGI result", "value": int((cmap["n_figi_results"] > 0).sum())},
    {"check": "CUSIPs mapped through the ID_CINS retry", "value": int((cmap["map_source"] == "openfigi_cins").sum())},
    {"check": "CUSIPs mapped from the hand-reviewed manual map", "value": int((cmap["map_source"] == "manual").sum())},
    {"check": "CUSIPs mapped to US common equity (incl. REITs)", "value": int(is_common.sum())},
    {"check": "universe stock-quarters", "value": len(universe)},
    {"check": "universe quarters with < UNIVERSE_SIZE stocks", "value": int((universe.groupby("quarter").size() < config.UNIVERSE_SIZE).sum())},
    {"check": "excluded candidates that need review (no match / no U.S. listing) and would be in the top N", "value": int((review & (ex["quarters_in_top_n"] > 0)).sum())},
    {"check": "universe rows where 13F name first word != OpenFIGI name first word", "value": int((~universe["name_match"]).sum())},
])
report.to_csv(config.TABLES / "cusip_mapping_report.csv", index=False)
(universe[~universe["name_match"]]
 .drop_duplicates("cusip")[["cusip", "ticker", "issuer", "figi_name", "map_source"]]
 .to_csv(config.TABLES / "cusip_name_mismatches.csv", index=False))
print(report.to_string(index=False))
print("Excluded candidates and reasons: outputs/tables/universe_exclusions.csv")
print("Name mismatches to eyeball: outputs/tables/cusip_name_mismatches.csv")
if (review & (ex["quarters_in_top_n"] > 0)).any():
    print("WARNING: some large stocks have no current U.S. listing and are not in "
          "data/manual_ticker_map.csv. Review outputs/tables/universe_exclusions.csv "
          "and add the real ones to the manual map.")
print("Done.")
