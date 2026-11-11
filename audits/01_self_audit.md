# Self-audit 01: Checkpoint 2 (v0)

**Date:** 2026-11-11 (code complete; re-run and update before the Nov 14 PR)
**Scope:** whole repo at v0. The code was tested end to end on synthetic data in the real SEC/OpenFIGI/price formats (`tests/make_fake_raw.py`). The real-data v0 run (`CROWD_QUICK=1 python run_all.py`) must be completed and the numbers below filled in.

Before submitting, also run the Quick Reference's *Skeptical review* prompt on the repo and add its findings to the last section.

## The ten audit checks

| # | Check | Status | Evidence / where to look |
|---|---|---|---|
| 1 | **Reproduces** from raw inputs with one command | ✅ code / ⬜ real run | `run_all.py` runs `src/01`–`07`, stops on error. Tested on synthetic data in `tests/` |
| 2 | **Provenance** for every raw input | ✅ | `data/raw/provenance.csv`: URL, UTC pull time, bytes, SHA-256. OpenFIGI answers cached verbatim in `openfigi_cache.json` |
| 3 | **Unit of observation** is right; keys unique; merges validated | ✅ | Stock × quarter. `assert` on `(ticker, quarter)` and `(cusip, quarter)` in `05_build_dataset.py`. `validate=` on every merge/join. Manager-quarter and manager-stock-quarter uniqueness asserted in `02_parse_13f.py` |
| 4 | **No look-ahead** | ✅ | Only on-time original 13F-HR filings. Returns start the first trading day after quarter end + 45 days (asserted). Universe from point-in-time 13F holdings, not today's index. `lookahead_comparison.csv` shows the wrong-timing result |
| 5 | **No LLM leakage** | ✅ n/a | No LLM is used to make predictions or label data. LLMs were used only to help write code, which every teammate must be able to explain |
| 6 | **No p-hacking** | ✅ | Primary spec pre-registered in `specs_tried.md`. All specs auto-logged to `outputs/tables/specs_run.csv` (13) |
| 7 | **Magnitudes, not just stars** | ✅ | `outputs/tables/magnitude.csv`: gross spread, turnover, cost at 10 bp/side, net and annualized |
| 8 | **Checks by hand** | ✅ code / ⬜ real run | `07_hand_checks.py`: holder count from raw zips, one return from raw prices, one formation date, one quarter's Q5 − Q1 by plain sorting. Output `outputs/tables/hand_checks.csv` |
| 9 | **Honest limits** | ✅ | README "Threats to validity" (9 items) |
| 10 | **We understand it** | ⬜ | Each teammate walks through one script out loud before Nov 14 (assign below) |

## Numbers to fill in after the real v0 run

| Item | Value | Source file |
|---|---|---|
| Manager filings kept / dropped as late | | `outputs/tables/filing_filter_counts.csv` |
| Candidate CUSIPs mapped to U.S. common stock | | `outputs/tables/cusip_mapping_report.csv` |
| Name mismatches reviewed by hand (how many were real errors?) | | `outputs/tables/cusip_name_mismatches.csv` |
| Stock-quarters missing a forward return | | `outputs/tables/return_coverage.csv` |
| All four hand checks match? | | `outputs/tables/hand_checks.csv` |

## Known open issues (what an auditor would attack first)

1. **Survivorship in Yahoo returns.** Delisted tickers have no prices, so those stock-quarters drop out. The rate is measured but not fixed. Fix: CRSP via WRDS, or check delisted names by hand.
2. **OpenFIGI returns today's ticker.** Reused tickers can map a 2022 CUSIP to a different company. Mitigated by the name-mismatch list, which must actually be reviewed.
3. **Holder counts include every 13F manager** (banks, pensions, index funds), not just hedge funds. Index-fund holders barely change, so `dbreadth` is driven by active managers, but this should be confirmed.
4. **Size proxy.** The universe and the size control use 13F institutional dollar holdings, not market cap.
5. **Short sample.** 12 quarters means the t-statistics have 11 degrees of freedom.

## Who explains what (check 10)

| Script | Teammate |
|---|---|
| `01_download_13f.py`, `02_parse_13f.py` | |
| `03_universe_and_cusip_map.py`, `04_download_prices.py` | |
| `05_build_dataset.py` | |
| `06_analysis.py`, `07_hand_checks.py`, `app.py` | |

## Skeptical-review findings and fixes

| Finding | Fix / response | Commit |
|---|---|---|
| | | |
