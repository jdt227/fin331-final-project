# Self-audit 01: Checkpoint 2 (v0)

**Date:** 2026-11-14 · **Branch:** `Harrison` · **Run audited:** `CROWD_QUICK=1 python run_all.py` (2023, top 100 stocks, 400 stock-quarters), log in `run_log.txt`.

**Prompt used** (Quick Reference, *Starter prompts for coding agents* #5), verbatim:
> "Review this repo like a skeptical finance professor. Look for look-ahead bias and leakage, merges without `validate`, unit and frequency mismatches, hard-coded paths or keys, and steps that don't reproduce from `run_all.py`. List issues ranked by severity; don't fix anything yet."

We checked every finding against the code and the real v0 files before deciding whether it was real.

---

## 1. What it flagged, and which findings are real

Ranked by severity. **Real?** = we confirmed it in the code or data.

| # | Severity | Finding | Real? | Evidence |
|---|---|---|---|---|
| R1 | **Critical** | **The universe is filtered by what OpenFIGI knows today, not by what existed then.** That is survivorship bias, a form of look-ahead. 11 of 200 candidate CUSIPs got no OpenFIGI match: foreign CINS codes (Linde, Medtronic, Accenture, Chubb, Eaton, Aon, NXP, ASML) and CUSIPs that later changed (Lam Research, Canadian Pacific, Honeywell). Firms acquired since 2023 resolve only to foreign listings and are dropped: Activision → `ATVIEUR`, VMware → `VMWEUR`, Pioneer → `PXDEUR`. Exxon maps to `EXMOC` (exchange `CP`) and is dropped. REITs (Prologis and others, `securityType2 = REIT`) fail the `Common Stock` filter. | **Yes** | `data/raw/cusip_ticker_map.csv`: 161 Common Stock, 21 funds, 11 no match, 4 REIT, 3 ADR. The "0 of 400 missing returns" result does **not** rule out survivorship: delisted names were removed in step 3, before prices were pulled. The earlier "0 name-mismatch errors" checked only stocks that were *included* |
| R2 | **High** | **The committed repo does not reproduce.** `run_all.py` now calls `src/08_export_site_data.py`, but that file, `index.html`, `outputs/`, `data/raw/provenance.csv`, `data/raw/cusip_ticker_map.csv` and `data/raw/openfigi_cache.json` are untracked. A fresh clone fails at step 8. It also re-queries OpenFIGI *today*, so the mapping can change. `app.py` was deleted locally, but the deletion isn't committed. | **Yes** | `git ls-files`, `git status` |
| R3 | **High** | **Inference is overstated.** Every time-series t-stat uses 4 quarterly observations (3 df). Two-sided p-values: Q5 − Q1 t = 2.42 → **p = 0.094**; Fama–MacBeth t = 2.67 → **p = 0.076**; pooled OLS t = 1.23 → p = 0.31. One of the 4 quarters is negative (2023Q4: −1.3%). The dashboard headline says the result "supports the information story", and neither the dashboard nor the proposal reports p-values or df. | **Yes** | `long_short_summary.csv`, `fama_macbeth.csv`, `pooled_ols.csv`, `long_short_by_quarter.csv`, `index.html` l. 524 |
| R4 | **High** (full sample) | **The 45-day deadline isn't moved past weekends.** In the full sample, the 2022Q1 deadline (15 May 2022) and the 2022Q2 deadline (14 Aug 2022) fall on Sundays, so the legal deadline is the following Monday. Filings made that Monday are dropped as "late". Many managers file on the last day, so this removes a large group of managers. It also removes them from the continuing-filer set behind `dbreadth` for 2022Q1–Q3. This is not look-ahead (it errs conservative), but it distorts the signal. | **Yes** (0 v0 quarters affected) | `config.filing_deadline`; calendar check of all 13 report quarters |
| R5 | Medium | **The price cache ignores the date window.** Step 4 skips any ticker already in `prices_daily.parquet`. All cached series run from 2022-09-20 to 2024-06-03, the v0 window. A default full run then crashes in step 5 ("extend PRICE_END") rather than producing silently wrong numbers. But a change that only moves the *start* earlier would silently set 2022 formation dates to 2022-09-20. The earlier draft called this "silent" in every case. That is only partly right. | **Yes** (downgraded from High) | `04_download_prices.py` (`done = set(have["ticker"])`); price file date range |
| R6 | Medium | **New CUSIPs look as crowded as possible.** `fillna(0)` on `breadth_lag` means a spinoff, IPO or CUSIP change gets `dbreadth` equal to its whole breadth and lands in Q5 by construction. | Real but **latent**: 0 cases in v0 (`breadth_lag == 0`: 0 rows) | `05_build_dataset.py` |
| R7 | Medium | **One company counted twice.** GOOG and GOOGL are both in the universe in all 4 quarters. Deduplication is by ticker, not by issuer. | **Yes** | `final_dataset.parquet` |
| R8 | Medium | **One-stock sensitivity.** Dropping NVDA cuts Q5 − Q1 from +5.98% to +4.69% per quarter (t = 2.08, p = 0.13). Quintiles hold 20 equal-weighted names. | **Yes** | Diagnostic run, logged in `specs_tried.md` |
| R9 | Medium | **Reproducing depends on the mode and on Yahoo.** The committed numbers come from `CROWD_QUICK=1`, but plain `python run_all.py` is the full sample. `prices_daily.parquet` is git-ignored, so a re-run re-pulls Yahoo, and `prices_tried_empty.txt` carries state from one run to the next. | **Yes** | `.gitignore`, `README.md` |
| R10 | Low | **Strongest secondary result is highlighted.** `PROPOSAL.md` reports the `n_holders` *level* Fama–MacBeth coefficient (t = −3.9, p = 0.03 with 3 df). That is the strongest of 13 specifications and not the pre-registered signal. It is logged, so this isn't hidden p-hacking, but it should be labeled exploratory. | **Yes** | `PROPOSAL.md` l. 154, `specs_run.csv` |
| R11 | Low | **Benchmark mismatch.** Equal-weighted quintiles are compared with cap-weighted SPY, so quintile *levels* are off (the universe averaged −0.3%/qtr vs SPY). The Q5 − Q1 spread is unaffected. | **Yes** | `final_dataset.csv` |
| R12 | Low | **Docs are out of date.** The README "Threats to validity" says the sample has 12 quarters (v0 has 4). The earlier audit said `run_all.py` runs steps 01–07 (it runs 01–08). | **Yes** | `README.md` l. 108 |
| R13 | Low | **Hand check C isn't fully independent.** It rebuilds the formation date from the same cached SPY calendar the pipeline uses, so it would not catch R5. | **Yes** | `07_hand_checks.py` |
| R14 | Low | **Hard-coded defaults.** `tests/make_fake_raw.py` defaults to `/tmp`, which fails on Windows. The SEC file list must be extended by hand after Feb 2026. `data/interim/holdings_parts/` isn't cleared between runs. That last one is harmless today: the `(cik, cusip)` uniqueness assert would catch a double count. | **Yes** | code |

**Checked and clean.** These are the prompt's other targets.
- **Merges:** every `merge`/`join` passes `validate=` (steps 2, 3 and 5, confirmed by grep), and keys are asserted unique.
- **Keys and paths:** no API keys, emails or absolute paths in code. Keys come only from environment variables.
- **Units:** the 13F `VALUE` change from $000s to dollars is handled by filing date, and split adjustment is applied for net buyers.
- **Return timing:** each return starts on the first trading day after the deadline (e.g. 2023Q1 → 16 May 2023) and runs to the next formation date, so holding periods don't overlap. `ret_past` and `vol_63d` use only prices up to the formation date.
- **Dashboard:** it reads only `outputs/`.

---

## 2. What we fixed in this PR, and what's still open

**Fixed in this PR**

| Fix | Where |
|---|---|
| The OpenFIGI cache write crashed inside OneDrive (`Errno 22`, file locked mid-write). Fix: write to a temp file, swap it in, retry up to 10 times; save the cache every 10 batches | `common.safe_write_text`, step 3 |
| A transient Yahoo failure (QCOM, "database is locked") was recorded as permanent "no data". Fix: retry each missing ticker on its own, twice. QCOM recovered; both runs are logged in `specs_tried.md` | step 4 |
| Replaced the Streamlit `app.py` with a static `index.html`, built from `outputs/` by the new step 8, which `run_all.py` runs. Every number on the site traces to a file in `outputs/` | `src/08_export_site_data.py`, `run_all.py` |
| Real-data v0 run completed, and all 4 hand checks match | `run_log.txt`, `outputs/tables/hand_checks.csv` |
| **Before merging (R2):** `git add` `src/08_export_site_data.py`, `index.html`, `outputs/`, `data/raw/{provenance.csv, cusip_ticker_map.csv, openfigi_cache.json}`, `run_log.txt`, `images/dashboard_v0.png`, and commit the `app.py` deletion | git |

**Still open, with our plan** (none of the review's findings are fixed in code yet, per the "don't fix anything yet" instruction)

| # | Plan | When |
|---|---|---|
| R1 | Re-query unmatched CUSIPs with `ID_CINS`. Accept REIT common equity. When there's no current U.S. listing, take the ticker from the U.S. listing including inactive ones (or a small hand-made map), and keep the stock. Write every excluded candidate, with a reason, to `outputs/tables/universe_exclusions.csv` | Before the full-sample run |
| R2 | Commit the files listed above; confirm a fresh clone runs `CROWD_QUICK=1 python run_all.py --from 5` | This PR |
| R3 | Report p-values with df in `06_analysis.py`, the proposal and the dashboard. Label v0 "not significant at 5%" and remove the "supports the information story" wording until the full sample is in | This PR (text) / next PR (code) |
| R4 | Move `filing_deadline` to the next business day when day 45 isn't one; re-check that the formation date follows it | Before the full-sample run |
| R5 | Store each ticker's pulled date range; re-download when the needed window isn't covered; assert formation date − deadline < 7 days | Before the full-sample run |
| R6 | Require holders in both quarters (or link old → new CUSIP); count and report excluded cases | Full sample |
| R7 | Keep one share class per issuer (the larger by 13F dollars) | Full sample |
| R8 | Report leave-one-out, winsorized and value-weighted spreads | v1 |
| R9 | Say in the README which command made the committed outputs; commit prices (≈0.4 MB) or a hash plus a re-pull check | This PR (README) |
| R10 | Label the `n_holders` level result "exploratory, not pre-registered" in `PROPOSAL.md` | This PR |
| R11 | Also report returns relative to the equal-weighted universe | v1 |
| R12 | Fix the README and audit wording | This PR |
| R13 | Have check C use an independent calendar (e.g. `pandas_market_calendars`) or check a raw Yahoo date | v1 |
| R14 | Use `tempfile` in tests; clear `holdings_parts/` at the start of step 2; document the SEC file list | v1 |

Other known limits, unchanged: holder counts include every 13F manager (banks, pensions, index funds), not just hedge funds. The size control is 13F institutional dollars, not market cap. Yahoo has no prices for delisted tickers, so CRSP via WRDS would be better.

---

## 3. The 10-point checklist (`00_PROJECT_SEEDS`)

| # | Check | Status | One line |
|---|---|---|---|
| 1 | Reproduces from raw with one command | **problem** | Works locally, but step 8, `index.html` and the mapping/provenance files aren't in git (R2); cached prices block the full sample (R5) |
| 2 | Provenance for every raw input | **problem** | `provenance.csv` has URL, UTC time, bytes and SHA-256 for every input, but it and the OpenFIGI cache aren't committed yet (R2) |
| 3 | Unit of observation; unique keys; validated merges | **problem** (minor) | Stock × quarter, keys asserted, every merge validated, but GOOG/GOOGL double-count one issuer (R7) |
| 4 | No look-ahead | **problem** | Return timing is correct (start = first trading day after deadline, asserted), but the universe uses today's OpenFIGI, which drops delisted/acquired firms (R1) |
| 5 | No LLM leakage | **OK** | No LLM makes predictions or labels data; LLMs only helped write code |
| 6 | No p-hacking | **OK** | `dbreadth` pre-registered; all 13 specs auto-logged in `specs_run.csv`; secondary result to be labeled exploratory (R10) |
| 7 | Magnitudes, not just stars | **OK** | `magnitude.csv`: +5.98% gross, 64% leg turnover, 0.26% cost, +5.72% net per quarter (sensitive to NVDA, R8) |
| 8 | Checks by hand | **OK** | 4 of 4 match: AAPL 2023Q3 holders 4,240; return −2.08%; formation 15 Nov 2023; Q5 − Q1 9.74% (check C shares the price calendar, R13) |
| 9 | Honest limits | **problem** | README lists 9 threats, but says 12 quarters, and the p-values (0.09 / 0.08) aren't shown anywhere (R3, R12) |
| 10 | We understand it | **not yet** | Scripts assigned (below); walk-throughs not yet done |

### Numbers from the v0 run

| Item | Value | Source |
|---|---|---|
| Manager filings kept / dropped | 33,529 kept; 1,594 late; 2 duplicate originals | `filing_filter_counts.csv` |
| Candidate CUSIPs mapped to U.S. common stock | 154 of 200 (see R1 for the rest) | `cusip_mapping_report.csv` |
| Name mismatches among included stocks | 7 CUSIPs, 0 errors (renames such as Raytheon→RTX, Schlumberger→SLB) | `cusip_name_mismatches.csv` |
| Stock-quarters missing a forward return | 0 of 400 (not evidence against survivorship, see R1) | `return_coverage.csv` |

### Who explains what (check 10)

| Script | Teammate | Must be able to explain |
|---|---|---|
| `01_download_13f.py`, `02_parse_13f.py` | Brauston Estes | Why SEC files are by filing date; the 45-day rule (and R4); why amendments and late filings are dropped; $000s → $ |
| `03_universe_and_cusip_map.py`, `04_download_prices.py` | Jacob Thompson | How the top-N universe is picked and where it still has survivorship (R1); the OpenFIGI mapping; the price cache (R5) |
| `05_build_dataset.py`, `run_all.py` | Harrison Babuschak | Formation date vs. quarter end; `dbreadth`, `net_buyer_frac`, split adjustment; why keys are unique |
| `06_analysis.py`, `07_hand_checks.py`, `08_export_site_data.py`, `index.html` | Juliana Vasquez | Quintile sorts; Fama–MacBeth vs. pooled OLS and why 3 df matters (R3); the cost calculation; what each hand check recomputes |

For any step, everyone should be able to answer: *what information was public on that date?*
