# Self-audit 01: Checkpoint 2 (v0)

**Date:** 2026-11-14 · **Branch:** `Harrison` · **Run audited:** `CROWD_QUICK=1 python run_all.py` (2023, top 100 stocks, 400 stock-quarters).

**Prompt used** (Quick Reference, *Starter prompts for coding agents* #5), verbatim:
> "Review this repo like a skeptical finance professor. Look for look-ahead bias and leakage, merges without `validate`, unit and frequency mismatches, hard-coded paths or keys, and steps that don't reproduce from `run_all.py`. List issues ranked by severity; don't fix anything yet."

We ran it on the first v0 run, checked every finding against the code and the real v0 files, then fixed what we could in this PR and re-ran v0.

---

## 1. What it flagged, and which findings are real

Ranked by severity. **Real?** = we confirmed it in the code or the v0 data.

| # | Severity | Finding | Real? | Evidence |
|---|---|---|---|---|
| R1 | **Critical** | **The universe was filtered by what OpenFIGI knows today, not by what existed then.** That is survivorship bias, a form of look-ahead. In v0, 11 of 200 candidate CUSIPs got no match: foreign CINS codes (Linde, Medtronic, Accenture, Chubb, Eaton, Aon, NXP) and CUSIPs that later changed (Lam Research, Canadian Pacific, Honeywell). Firms acquired since 2023 resolve only to foreign listings and were dropped: Activision → `ATVIEUR`, VMware → `VMWEUR`, Pioneer → `PXDEUR`. Exxon mapped to `EXMOC` (exchange `CP`). REITs (Prologis, American Tower, Equinix, Crown Castle) failed the `Common Stock` filter. 12 large stocks were missing from the v0 top 100 | **Yes** | `data/raw/cusip_ticker_map.csv` (first run): 161 Common Stock, 21 funds, 11 no match, 4 REIT, 3 ADR. The first run's "0 of 400 missing returns" did not rule out survivorship: delisted names were removed in step 3, before prices were pulled |
| R2 | **High** | **The committed repo did not reproduce.** `run_all.py` called `src/08_export_site_data.py`, but that file, `index.html`, `outputs/` and the cached raw inputs were untracked, so a fresh clone failed at step 8 and re-queried OpenFIGI *today* | **Yes** | `git ls-files`, `git status` |
| R3 | **High** | **Inference was overstated.** Every time-series t-stat uses 4 quarters (3 df). Two-sided p-values on the first run: Q5 − Q1 t = 2.42 → **p = 0.09**; Fama–MacBeth t = 2.67 → **p = 0.08**; pooled OLS t = 1.23 → p = 0.22. The dashboard said the result "supports the information story", and nothing reported p-values or df | **Yes** | `long_short_summary.csv`, `fama_macbeth.csv`, `pooled_ols.csv`, `index.html` |
| R4 | **High** (full sample) | **The 45-day deadline wasn't moved past weekends.** The 2022Q1 (15 May 2022) and 2022Q2 (14 Aug 2022) deadlines fall on Sundays, so the legal deadline is Monday. Monday filings would be dropped as "late", along with their managers' place in the continuing-filer set behind `dbreadth` for 2022Q1–Q3 | **Yes** (no v0 quarter affected) | `config.filing_deadline`; calendar check of all 13 report quarters |
| R5 | Medium | **The price cache ignored the date window.** Step 4 skipped any ticker already cached. After the v0 run, a full run would crash in step 5 ("extend PRICE_END"); a change that only moved the start earlier would *silently* set 2022 formation dates to 2022-09-20. (The first write-up called it silent in every case; the default full run actually crashes) | **Yes** | `04_download_prices.py`; cached prices all run 2022-09-20 to 2024-06-03 |
| R6 | Medium | **New CUSIPs looked as crowded as possible.** `fillna(0)` on `breadth_lag` put any IPO, spinoff or CUSIP change in Q5 by construction | **Yes**: 0 cases in the first v0 universe, but Linde (new CUSIP after its March 2023 reorganization) is one once the universe is fixed | `05_build_dataset.py`, `return_coverage.csv` |
| R7 | Medium | **One company counted twice:** GOOG and GOOGL were both in the universe in all 4 quarters (also BRK-A/BRK-B in the candidate pool) | **Yes** | `final_dataset.parquet` |
| R8 | Medium | **One-stock sensitivity.** Dropping NVDA cut Q5 − Q1 from +5.98% to +4.69% per quarter (t = 2.08, p = 0.13). Quintiles hold 20 equal-weighted names | **Yes** | Diagnostic run, logged in `specs_tried.md` |
| R9 | Medium | **Reproducing depended on Yahoo and on the mode.** `prices_daily.parquet` was git-ignored, so a re-run re-pulled Yahoo (whose adjusted prices change over time). The README didn't say which command made the committed outputs | **Yes** | `.gitignore`, `README.md` |
| R10 | Low | **The strongest secondary result was highlighted.** `PROPOSAL.md` quoted the `n_holders` *level* Fama–MacBeth coefficient (t = −3.9, p = 0.03), the strongest of 13 specifications and not pre-registered, without saying so | **Yes** | `PROPOSAL.md`, `specs_run.csv` |
| R11 | Low | **Benchmark mismatch.** Equal-weighted quintiles vs. cap-weighted SPY: quintile *levels* are off (the universe averaged −0.3%/qtr vs SPY); the Q5 − Q1 spread is unaffected | **Yes** | `final_dataset.csv` |
| R12 | Low | **Docs out of date:** the README said 12 quarters (v0 has 4); the audit said `run_all.py` runs steps 01–07 (it runs 01–08) | **Yes** | `README.md` |
| R13 | Low | **Hand check C wasn't independent of the pipeline's calendar** (both used cached SPY dates), so it couldn't catch R5 | **Yes** | `07_hand_checks.py` |
| R14 | Low | **Hard-coded defaults / stale state:** `tests/make_fake_raw.py` defaulted to `/tmp` (fails on Windows); step 2 read every old file in `holdings_parts/`, including ones from an earlier sample | **Yes** | code |

**Checked and clean.** Every `merge`/`join` passes `validate=` (steps 2, 3, 5; confirmed by grep) and keys are asserted unique. No API keys, emails or absolute paths in code; keys come only from environment variables. The 13F `VALUE` unit change ($000s → $) is handled by filing date. Returns start the first trading day after the deadline and run to the next formation date, so holding periods don't overlap; `ret_past` and `vol_63d` use only prices up to the formation date. The dashboard reads only `outputs/`.

---

## 2. What we fixed in this PR, and what's still open

**Fixed in this PR**

| # | Fix | Where |
|---|---|---|
| R1 | REIT common shares count as common stock. Unmatched CINS codes are retried with OpenFIGI's `ID_CINS` lookup. Stocks with no current U.S. listing (acquired, changed CUSIP, foreign-incorporated) are kept through `data/manual_ticker_map.csv`: 18 hand-reviewed rows, each with the reason and source (ASML's NY-registry shares are reviewed and excluded, like ADRs). Every large candidate still excluded is written, with its reason, to `outputs/tables/universe_exclusions.csv` and shown on the dashboard; step 3 warns if one needs review | `src/03_universe_and_cusip_map.py`, `data/manual_ticker_map.csv` |
| R2, R9 | All pipeline files, `outputs/` and the cached inputs (`openfigi_cache.json`, `prices_daily.parquet`, `prices_requests.csv`, `provenance.csv`) are committed, so a fresh clone reproduces the exact numbers. The README says which command made the committed outputs | `.gitignore`, `README.md` |
| R3 | Every sort, Fama–MacBeth and pooled-OLS table reports a p-value (t distribution with n − 1 df for time-series tests). The dashboard headline shows p and df and says whether the result is significant at 5% | `src/06_analysis.py`, `index.html`, `PROPOSAL.md` |
| R4 | The deadline moves to the next business day when day 45 is a weekend or federal holiday. Formation dates follow it | `src/config.py` |
| R5 | Step 4 logs the window requested for each ticker (`prices_requests.csv`) and re-downloads, replacing all old rows, when the cached window doesn't cover the sample. Step 5 asserts every formation date is 1–7 days after its deadline | `src/04_download_prices.py`, `src/05_build_dataset.py` |
| R6 | Stocks with no 13F holders last quarter get no change measures; `return_coverage.csv` counts them | `src/05_build_dataset.py` |
| R7 | One share class per issuer (first six CUSIP characters): the class held by the most 13F managers; asserted | `src/03_universe_and_cusip_map.py` |
| R10 | The `n_holders` level result is labeled exploratory in the proposal | `PROPOSAL.md` |
| R12 | README threats-to-validity rewritten (12 items) | `README.md` |
| R13 | Hand check C re-derives the business-day deadline with its own code and uses the stock's own trading dates | `src/07_hand_checks.py` |
| R14 | Test data goes to the system temp folder by default; step 2 reads only the parts it wrote in this run | `tests/make_fake_raw.py`, `src/02_parse_13f.py` |
| — | Earlier fixes: OneDrive file-lock crash (`common.safe_write_text`); transient Yahoo failures retried per ticker; the Streamlit app replaced by a static `index.html` built from `outputs/` by step 8 | `src/common.py`, steps 3, 4, 8 |

**v0 results after the fixes** (`CROWD_QUICK=1 python run_all.py`): `dbreadth` Q5 − Q1 is **+5.18% per quarter, t = 2.11, p = 0.13 with 3 df**, positive in 3 of 4 quarters; +4.93% after costs. Not significant at 5%, and the proposal and dashboard say so. All 400 stock-quarters have a forward return; all 4 hand checks match; no large candidate is left needing review.

**One more problem the re-run found, and fixed.** The share-class rule first kept the class with the larger 13F dollar holdings. That picked BRK-A in 2023Q2–Q4, because some filers report Class B share counts under the Class A CUSIP: 13F "holdings" of BRK-A reached $1.2 trillion in 2023Q2, more than Berkshire's market value. The rule now keeps the class with the most 13F holders (BRK-B and GOOGL in every quarter). Logged in `specs_tried.md`. The same misreporting can inflate the size ranking of other high-priced stocks; see the open items.

**How we tested the fixes.** `tests/make_fake_raw.py` now plants a trap for each one: a second share class, a new listing, a REIT, a stock with only a foreign listing, and the 2022 weekend deadlines. The full 12-quarter pipeline passes on it, and each trap is handled as intended. Steps 3–6 were also re-run on the real 2023 holdings: the new rules add ACN, AMT, BLK, CB, EQIX, ETN, HON, LIN, LRCX, MDT, PLD and XOM to the top 100 and drop GOOG as a second class. The complete v0 outputs in this PR come from a re-run of `CROWD_QUICK=1 python run_all.py` with the fixed code; the changes are logged in `specs_tried.md`.

**Still open, with our plan**

| # | Plan | When |
|---|---|---|
| R1 (full sample) | The full top-500 sample will surface more acquired firms and changed CUSIPs. Review every "needs review" row in `universe_exclusions.csv` and add the real ones to `data/manual_ticker_map.csv` | With the v1 run (Nov 21) |
| Returns survivorship | Yahoo has no prices for delisted tickers (ATVI, PXD, VMW and others), so those stock-quarters lose their return. The rate is reported in `return_coverage.csv`. Fix: CRSP via WRDS, or hand-collect the final prices of the largest delisted names | Ask Prof. Bowen about WRDS; v1 |
| R8 | Report leave-one-out, winsorized and value-weighted spreads (after the fixes, dropping NVDA gives +4.11%, p = 0.16) | v1 |
| R11 | Also report returns relative to the equal-weighted universe | v1 |
| Size ranking | Misreported share counts (as with BRK-A) can inflate a high-priced stock's 13F dollar holdings and its size rank. Cap each stock's 13F shares at its shares outstanding, or rank by market cap from another source | v1 |
| CUSIP changes | Link old → new CUSIPs (Linde 2023) so the change measures carry across corporate actions instead of being left empty | v1 |
| Coverage | Holder counts include every 13F manager, not just hedge funds; the size control is 13F institutional dollars, not market cap | Stretch: hedge-fund subset |

---

## 3. The 10-point checklist (`00_PROJECT_SEEDS`)

| # | Check | Status | One line |
|---|---|---|---|
| 1 | It reproduces | **OK** | `python run_all.py` rebuilds everything from raw inputs; cached OpenFIGI and Yahoo answers are committed; the 12-quarter offline test passes end to end |
| 2 | Every input has a provenance | **OK** | `data/raw/provenance.csv` (URL, UTC pull time, bytes, SHA-256), `prices_requests.csv` (window per ticker), and a reason and source on every row of `manual_ticker_map.csv` |
| 3 | The unit of observation is right | **OK** | Stock × quarter; `(ticker, quarter)`, `(cusip, quarter)` and one-issuer-per-quarter asserted; every merge uses `validate=` |
| 4 | No look-ahead | **OK** | Returns start the first trading day after the business-day deadline (asserted); late filings and amendments dropped; universe no longer limited to today's survivors |
| 5 | No LLM leakage | **OK** | No LLM makes predictions or labels data; LLMs only helped write code |
| 6 | No p-hacking | **OK** | `dbreadth` pre-registered; all 13 specs auto-logged; definition changes logged before any full-sample results; exploratory result labeled |
| 7 | Magnitudes, not just stars | **OK** | `magnitude.csv`: +5.18% gross per quarter, 62% leg turnover, 0.25% cost, +4.93% net |
| 8 | Checks by hand | **OK** | 4 of 4 match: AAPL 2023Q3 holders 4,240 from the raw zips; return −2.08%; formation 15 Nov 2023; that quarter's Q5 − Q1 9.28% |
| 9 | Honest limits | **OK** | README lists 12 threats; p-values with df everywhere; returns survivorship disclosed and measured |
| 10 | We understand it | **not yet** | Scripts assigned below; walk-throughs before Nov 21 |

### Who explains what (check 10)

| Script | Teammate | Must be able to explain |
|---|---|---|
| `01_download_13f.py`, `02_parse_13f.py` | Brauston Estes | Why SEC files are by filing date; the 45-day rule and the business-day roll; why amendments and late filings are dropped; $000s → $ |
| `03_universe_and_cusip_map.py`, `04_download_prices.py` | Jacob Thompson | How the top-N universe avoids survivorship (manual map, exclusions report); one class per issuer; why the price cache tracks its date window |
| `05_build_dataset.py`, `run_all.py` | Harrison Babuschak | Formation date vs. quarter end; `dbreadth`, `net_buyer_frac`, the split adjustment and the new-CUSIP rule; why keys are unique |
| `06_analysis.py`, `07_hand_checks.py`, `08_export_site_data.py`, `index.html` | Juliana Vasquez | Quintile sorts; Fama–MacBeth vs. pooled OLS and why 3 df matters; the cost calculation; what each hand check recomputes |

For any step, everyone should be able to answer: *what information was public on that date?*
