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
| 2026-11-14 | Harrison | 2023 (`CROWD_QUICK=1`), top 100 | v0 run, all 13 specs. QCOM was missing (transient Yahoo error) | `dbreadth` Q5 − Q1 +6.07%/qtr, t = 2.13 | Superseded by the next row |
| 2026-11-14 | Harrison | 2023 (`CROWD_QUICK=1`), top 100 | Same 13 specs after fixing the download retry; QCOM now included. No definitions changed | `dbreadth` Q5 − Q1 +5.98%/qtr, t = 2.42; FM +1.12%/SD, t = 2.67; pooled OLS t = 1.23; look-ahead timing +7.54%. `n_holders` level FM −2.09%/SD, t = −3.94 | Superseded by the 2026-11-14 definition-change row below |
| 2026-11-14 | Harrison (skeptical review) | 2023 v0 | Diagnostic only, not new results: (a) drop stocks with no prior-quarter holders; (b) drop NVDA | (a) no change, 0 such stocks; (b) Q5 − Q1 +4.69%/qtr, t = 2.08 | Diagnostic (see audit R4, R6) |
| 2026-11-14 | Harrison (fixes from the skeptical review) | All | **Definition changes, made after seeing v0 and before any full-sample results.** None changes the signal, the test or the timing rule; they fix sample construction. (1) Universe: REIT common shares count as common stock; foreign-incorporated U.S.-listed ordinary shares kept (OpenFIGI `ID_CINS` retry + `data/manual_ticker_map.csv`); acquired firms and changed CUSIPs kept through the manual map; one share class per issuer. (2) Filing deadline moves to the next business day when day 45 is a weekend or holiday. (3) Stocks with no 13F holders last quarter get no change measures. (4) p-values with degrees of freedom added to every test | v0 re-run with these rules: `dbreadth` Q5 − Q1 +5.18%/qtr, t = 2.11, p = 0.13 (3 df), positive 3 of 4 quarters; net of costs +4.93%; FM +0.91%/SD, t = 2.17, p = 0.12; pooled OLS +1.06%, t = 1.15, p = 0.25; look-ahead timing +6.81%. `n_holders` level: pooled OLS −2.06%/SD, p = 0.01; FM −2.10%/SD, p = 0.09. Universe gains ACN, AMT, BLK, CB, EQIX, ETN, HON, LIN, LRCX, MDT, PLD, XOM; GOOG dropped as a second class; Linde 2023Q1 has no change measures (new CUSIP after its 2023 reorganization) | **Yes (current v0 result)** |
| 2026-11-14 | Harrison | 2023 v0 | Share-class rule changed from "larger 13F dollars" to "more 13F holders" after BRK-A was picked in 2023Q2–Q4: some filers report Class B share counts under the Class A CUSIP, which put $1.2 trillion of BRK-A in 13F holdings. Now BRK-B every quarter | Primary spread +5.19% → +5.18%; no other result changes materially (numbers in the row above are after this fix) | Yes |
| 2026-11-14 | Harrison | 2023 v0 | Diagnostic only: drop NVDA, with the fixed universe | Q5 − Q1 +4.11%/qtr, t = 1.84, p = 0.16 | Diagnostic (audit R8) |
| | | 2022–2024 | v1 full sample | | |

Rules for this log: add a row *every time* you change a definition, filter or sample and look at results. Never delete rows.
