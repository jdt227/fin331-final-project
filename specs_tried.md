# Specifications tried

Every specification we run goes here, **including the ones that didn't work**. `src/06_analysis.py` also writes an automatic, complete list of the specifications it runs to `outputs/tables/specs_run.csv`. This file adds the human decisions behind them: why we tried something, and what we changed afterward.

## Pre-registered primary specification (fixed on 2026-11-11, before full-sample results)

| Item | Choice |
|---|---|
| Signal | `dbreadth`: change in ownership breadth among managers filing in both quarters (Chen, Hong & Stein 2002) |
| Universe | 500 largest U.S. common stocks by 13F institutional dollar holdings, each quarter |
| Sample | Report quarters 2022Q1–2024Q4 |
| Timing | Buy at the close of the first trading day after quarter end + 45 days; hold until the next such date |
| Return | Holding-period return minus SPY over the same window (`exret_fwd`) |
| Test | Quintile sort, Q5 − Q1, t-stat across quarters; Fama–MacBeth with past return, 63-day volatility and log institutional dollars as controls |
| Costs | 10 bp per side × quintile turnover |

## Secondary specifications (reported in full, not used to pick a winner)

| # | Signal | Return | Method | Purpose |
|---|---|---|---|---|
| S1 | `pct_chg_holders` | `exret_fwd` | sort + FM + pooled OLS | Simplest "how many more holders" measure |
| S2 | `net_buyer_frac` | `exret_fwd` | sort + FM + pooled OLS | Herding-style buyers vs. sellers (Lakonishok, Shleifer & Vishny 1992) |
| S3 | `n_holders` (level) | `exret_fwd` | sort + FM + pooled OLS | Level of crowding rather than the change |
| S4 | `dbreadth` | `exret_naive` (quarter-end timing) | sort | **Deliberately wrong** look-ahead timing, to show how much it matters |
| P | all four | `exret_fwd` | pooled OLS, quarter FE, clustered by stock | Robustness to Fama–MacBeth |

**Total so far:** 4 signals × 3 methods + 1 look-ahead sort = **13 specifications**. The exact count, with estimates, is in `outputs/tables/specs_run.csv`.

## Log of runs and changes

| Date | Who | Sample | What we ran / changed | Result (paste from outputs/) | Kept? |
|---|---|---|---|---|---|
| 2026-11-11 | | Fake test data | Built the pipeline; ran end to end on synthetic SEC-format data to test the code | Not a result; synthetic data only | n/a |
| | | 2023 (`CROWD_QUICK=1`) | v0 run | | |
| | | 2022–2024 | v1 full sample | | |

Rules for this log: add a row *every time* you change a definition, filter or sample and look at results. Never delete rows.
