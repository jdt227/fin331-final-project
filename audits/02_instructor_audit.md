# Instructor audit: Token Ticklers, Checkpoint 2

**Repo:** jdt227/fin331-final-project · **Audited commit:** `c7eaba5` (2026-11-14, merge of PR #3 into `main`) · **Seed:** 9, crowded trades: what happens when the hedge funds pile in?

> Note from your human teacher: This review is generated with minimal supervision from Opus 5.5-high. It is thorough, but can be too generous at times and doesn't know my taste for what is "good". Grades it and I would assign are correlated, but noisy, ok? If you want additional feedback from _me_, you need to find me before/after/during class or during office hours for a guaranteed speedy reply. I will try to respond to emails and issues, but can not respond to student inquiries around the clock across the final weeks of class. Response times will be unpredictable, though during Thanksgiving week, I will do my best to respond quickly virtually, as in person options will be nil.

## Summary

This is careful, well-documented v0 work. The timing rule handles 13F filing dates properly, survivorship is taken seriously, a primary specification is registered in advance, and the self-audit is genuinely skeptical. I recomputed your headline independently from `outputs/final_dataset.csv`. I also recomputed AAPL's forward return from a fresh price pull. Both match exactly, and your offline test runs all eight steps end to end. I could not rerun steps 1–2 on the real SEC files (see the run note under the table). The most important new problem is in the 13F dollar values themselves: in 2023Q2 they exceed market value for most of your universe, which distorts the size ranking that picks the top 100 and the size control (A1). The other findings are smaller.

| Check | Result |
|---|---|
| Reruns from scratch | ⚠️ the offline test (`tests/make_fake_raw.py` + `run_all.py`) passes all 8 steps. A real-data rerun was not possible in the audit environment (not your bug) |
| Inputs have provenance | ✅ `provenance.csv` (URL, UTC time, SHA-256), cached OpenFIGI and Yahoo answers, a reason and source for every manual map row |
| Keys unique, merges validated | ✅ `(ticker, quarter)` and `(cusip, quarter)` unique in `final_dataset.csv` (rechecked: 0 duplicates), `validate=` everywhere |
| No look-ahead / survivorship | ✅ formation is 1 day after the business-day deadline. Survivorship in returns is disclosed (A3) |
| LLM leakage handled | n/a |
| `specs_tried.md` complete | ✅ 13 specs, matching `specs_run.csv`, with definition changes and diagnostics logged |
| Magnitudes discussed | ✅ `magnitude.csv` (gross, turnover, costs, net) |
| Hand checks | ✅ 4 of 4 in `hand_checks.csv`. The auditor reproduced two of them independently |
| Threats to validity | ✅ 12 items. A1 adds one |
| Every number traces to `outputs/` | ⚠️ the NVDA leave-one-out numbers are only in `specs_tried.md` (A2) |

**Run note:** SEC returned its own 403 page ("Request Rate Threshold Exceeded") to the audit environment, which doesn't send a personal contact in the User-Agent. So steps 1–2 couldn't be rerun on the real 13F files, and steps 3–8 need their output.

## What holds up

- **Headline recomputed independently.** My own code sorts `dbreadth` into quintiles within each quarter from `outputs/final_dataset.csv`, with a bottom quintile of ⌊n/5⌋ stocks. It gives Q5 − Q1 = **0.05175 per quarter, t = 2.1097** (3 df), identical to `headline_numbers.json` and `long_short_by_quarter.csv` (0.0630, 0.0706, 0.0928, −0.0194).
- **One return recomputed from a fresh pull.** AAPL 2023Q3, from the 2023-11-15 close to the 2024-02-15 close, using a fresh yfinance pull: ret −0.020826, SPY +0.120898, excess −0.141723. Your values: −0.020825, 0.120898, −0.141723.
- **Seed 9, look-ahead from quarter-end dates:** returns start the first trading day after the business-day deadline, which is asserted. Late filings (1,594 in v0) and amendments are dropped. `lookahead_comparison.csv` shows the wrong timing would add 1.6 points per quarter.
- **Seed 9, CUSIP → ticker:** OpenFIGI, an `ID_CINS` retry, a hand-reviewed manual map, and a name-mismatch list. Example: CUSIP 571748102 maps to today's ticker MRSH, it is flagged in `cusip_name_mismatches.csv`, and its price history covers the sample (428 days, 2022-09-20 to 2024-06-03).
- **Seed 9, file size:** zips are git-ignored, small caches are committed, and the storage plan is in the README.
- **Offline test:** `tests/make_fake_raw.py` plants late filers, amendments, duplicates, the 2023 value-unit change, splits, a second share class, a REIT and a foreign-only listing. `run_all.py` passes all 8 steps on it (13 s in the audit environment).

## Findings

### A1 · Major · 2023Q2 13F dollar holdings exceed market value for most stocks, which distorts the size ranking and the size control

**Evidence:** I divided `inst_dollar` in `outputs/final_dataset.csv` by market value at quarter end (yfinance closes × historical shares outstanding). I used only the 108 stocks with no split since Oct 2022, so units match.

| Quarter | Median ratio | IQR | Stock-quarters with ratio > 1 |
|---|---|---|---|
| 2023Q1 | 0.75 | 0.67–0.82 | 2 of 86 |
| **2023Q2** | **1.27** | **0.82–1.85** | **53 of 85** |
| 2023Q3 | 0.71 | 0.64–0.79 | 0 of 87 |
| 2023Q4 | 0.75 | 0.68–0.80 | 0 of 86 |

Examples:
- MSFT: `inst_dollar` $2.86T in 2023Q2 vs $1.54T in Q1 and $1.56T in Q3, while `n_holders` barely moves (4,358 → 4,419 → 4,485).
- The universe total is $30.3T in Q2 vs $16.9–20.0T in the other quarters.
- **BAH** (Booz Allen) enters the top 100 only in 2023Q2, at rank 84, with $108.9B of 13F holdings: 7.45 × its market value.
- FISV goes from $62B (rank 98) to $139B (rank 61), 1.79 × its market value.

Which filer(s) cause it is **not verified**: the auditor couldn't download the SEC zips.

**Why it matters:** The universe is "the 100 largest stocks by 13F dollars". The inflation isn't uniform (Q2 IQR 0.82–1.85), so it changes who is in the 2023Q2 universe. It also adds noise to `log_inst_dollar`, a Fama–MacBeth control. Holder counts and `dbreadth` don't use values, so the signal itself is unaffected. Your self-audit's "size ranking" item suspected this for high-priced stocks after BRK-A. This shows it is broader, and concentrated in one quarter.

**Fix:**
1. Find the filer-level cause. Sum `SSHPRNAMT` by filer for 2023Q2 vs Q1 and look for a filer whose total jumps, or one reporting shares above shares outstanding.
2. Drop or cap holdings rows whose shares exceed the issuer's shares outstanding.
3. Better, rank the universe by market cap from price × shares outstanding (e.g. SEC XBRL `dei:EntityCommonStockSharesOutstanding`) instead of 13F dollars, and use that as the size control.
4. Add the ratio table above to `outputs/` as a check.

**How to show it's fixed:** An `outputs/` table of 13F dollars / market cap by quarter with no quarter's median above 1, and BAH out of the 2023Q2 universe (or a stated reason it belongs).

### A2 · Minor · Two reported numbers don't trace to `outputs/`, and the quintile convention is undocumented

**Evidence:**
- `PROPOSAL.md:162` and README threat 11 quote the NVDA leave-one-out result (+4.1% per quarter, p = 0.16). It appears only in `specs_tried.md:39`, not in any file in `outputs/`.
- With 99 stocks in 2023Q1 (Linde has no `dbreadth`), `06_analysis.py:40-45` puts 19 stocks in Q1 and 20 in Q5. A 20/19 split gives 2023Q1 = 0.0687 instead of 0.0630, and a mean spread of 0.0532 (t 2.15) instead of 0.0518.

**Fix:** Have `06_analysis.py` write the leave-one-out (and the value-weighted and winsorized versions you plan) to `outputs/tables/`. State the bin convention in `specs_tried.md`.

**How to show it's fixed:** The leave-one-out table exists in `outputs/tables/`, and `specs_tried.md` states the bin convention.

### A3 · Minor · Survivorship in returns becomes real at top 500

**Evidence:**
- `data/manual_ticker_map.csv` keeps ATVI, PXD, VMW and ANSS (delisted), and EA (taken private), to avoid survivorship in the universe.
- None of them has rows in `data/raw/prices_daily.parquet`.
- In v0 they all fall below the top-100 cutoff (minimum `inst_dollar` $62B–$87B by quarter), so `return_coverage.csv` correctly shows 0% missing. At top 500 they will enter the universe and lose their returns, which your threat 4 anticipates.

**Fix:** Before the v1 run, get these returns another way. CRSP via WRDS is best. Otherwise, use the cash or stock deal terms to build the final holding-period return (e.g. ATVI's $95 cash). Report `share_missing_return` by quarter, and the spread with and without hand-filled returns.

**How to show it's fixed:** `return_coverage.csv` for the full sample shows the hand-filled names with a source.

### A4 · Minor · The real-data steps can't be checked without SEC access, and versions aren't pinned

**Evidence:**
- `data/interim/` is git-ignored, so steps 3–8 can't run on real data without first re-downloading and parsing the SEC zips (steps 1–2).
- `requirements.txt` uses minimums only (e.g. `pandas>=2.1`, `yfinance>=0.2.54`). The audit environment resolved the versions listed in the run log.

**Fix:** Commit a compact parsed holdings file for the candidate pool (manager × CUSIP × quarter for the ~160 candidates, tens of MB), so steps 3–8 rerun offline. Then pin versions with `pip freeze`.

**How to show it's fixed:** A fresh clone with no network runs `python run_all.py --from 3` and reproduces `outputs/`.

## How to respond

This audit is `audits/02_instructor_audit.md` in your repo. Fix what you can, then add `audits/03_audit_response.md`, replying to each finding ID: fixed (the commit), disputed (why), or disclosed as a limitation (where).

**Deadline: Saturday, November 21, 2026.**
