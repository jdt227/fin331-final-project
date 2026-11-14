# Crowded Trades: What Happens When the Institutions Pile In?

**Team Token Ticklers:** Harrison Babuschak · Brauston Estes · Jacob Thompson · Juliana Vasquez
FIN 331 Data Science for Finance · Lehigh University · Fall 2026

---

## Summary

Every quarter, U.S. investment managers with more than $100 million in equities disclose their stock holdings to the SEC on Form 13F. When a large number of managers move into the same stock at the same time, the position becomes **crowded**. Crowded positions can unwind violently: if those same managers need to sell together, there are few natural buyers.

We will measure crowding for the 500 largest U.S. stocks every quarter from 2022 through 2024, using the SEC's free structured 13F data. We then test whether crowding predicts the stock's return over the following quarter. We use only the information that was actually public on each date.

We will deliver a **public dashboard that shows a crowding score for any large U.S. stock over time**, alongside the evidence on whether that score has historically predicted returns.

## Who would pay for this

**A risk manager at a hedge fund or long-only asset manager.** Their portfolio managers are rewarded for good ideas, and good ideas tend to be shared. A risk manager needs to know which positions are also held by many other funds, and whether that overlap has historically signalled weaker returns or sharper drawdowns. Many investment firms pay for tools that track crowded positions. We want to see whether publicly available SEC filings can provide similar information about potential investment risks.

## Research question

> **Do stocks that many institutions bought last quarter earn lower returns over the next quarter?**

Two economic stories predict opposite answers, which is what makes the question worth testing:

| Story | Prediction for crowded stocks | Prior evidence |
|---|---|---|
| **Price pressure and reversal.** Herding pushes prices above fundamentals, and they fall back. | Lower next-quarter returns | Lakonishok, Shleifer & Vishny (1992); Sias (2004) |
| **Informed buying.** When many managers independently buy a stock, they collectively know something. Also, if short sellers are constrained, falling breadth signals overpricing. | Higher next-quarter returns | Chen, Hong & Stein (2002); Brown, Howard & Lundblad (2022) find positive average returns but larger crashes in market sell-offs |

**Our hypothesis (stated before seeing the full-sample results):** the most crowded quintile underperforms the least crowded quintile over the next quarter, after the market return. We treat a positive spread as an equally informative answer, not a failure.

## Data

### The observation

One row is **one stock × one 13F report quarter.** The key `(ticker, quarter)` is unique (checked with `assert`), and every merge is validated.

### Columns of the final dataset (`outputs/final_dataset.csv`)

| Column | Meaning |
|---|---|
| `quarter` | 13F report quarter (holdings as of quarter end) |
| `ticker`, `cusip`, `issuer` | Identifiers |
| `n_holders`, `n_holders_lag` | Number of 13F managers holding the stock this quarter and last quarter |
| `pct_chg_holders` | Percentage change in the number of holders |
| `dbreadth` | **Primary signal.** Change in ownership breadth: among managers that filed in both quarters, the change in the share holding the stock (percentage points) |
| `net_buyer_frac` | (Buyers − sellers) / (buyers + sellers) among those managers, with shares adjusted for splits |
| `crowd_score` | Dashboard score, 0–100: average of the within-quarter percentile ranks of `n_holders` and `dbreadth` |
| `filing_deadline`, `formation_date`, `holding_end_date` | Quarter end + 45 days (next business day if that's a weekend or holiday); first trading day after it; next quarter's formation date |
| `ret_fwd`, `exret_fwd` | Return from formation date to holding end date; same minus SPY |
| `ret_past`, `vol_63d`, `log_inst_dollar` | Controls: prior-quarter return, 63-day volatility, log institutional dollar holdings |

### Real rows from the v0 run

Five stocks in report quarter 2023Q3, copied from `outputs/tables/sample_rows.md`. Holdings are as of 30 Sep 2023, public by the 14 Nov 2023 deadline, and the return runs from 15 Nov 2023 to 15 Feb 2024. Returns are decimals: 0.486 = 48.6%.

| quarter | ticker | n_holders | n_holders_lag | dbreadth | net_buyer_frac | crowd_score | formation_date | ret_fwd | exret_fwd |
|---|---|---|---|---|---|---|---|---|---|
| 2023Q3 | AAPL | 4240 | 4203 | 0.296 | -0.158 | 80.8 | 2023-11-15 | -0.021 | -0.142 |
| 2023Q3 | NVDA | 3381 | 3258 | 1.56 | 0.055 | 96.0 | 2023-11-15 | 0.486 | 0.365 |
| 2023Q3 | TSLA | 2675 | 2663 | 0.109 | 0.196 | 66.5 | 2023-11-15 | -0.175 | -0.295 |
| 2023Q3 | JPM | 3405 | 3355 | 0.53 | 0.001 | 85.2 | 2023-11-15 | 0.209 | 0.088 |
| 2023Q3 | XOM | 3301 | 3231 | 0.608 | 0.015 | 86.0 | 2023-11-15 | 0.010 | -0.111 |

Reading the NVDA row: 3,381 managers held it, up from 3,258. Among managers who filed in both quarters, the share holding NVDA rose 1.56 percentage points, which made it one of the most crowded stocks that quarter (score 96). It then beat SPY by 36.5% over the next quarter.

**v0 sample at a glance (2023, top 100 stocks):** 33,529 on-time original 13F filings kept (about 6,600–6,950 managers per quarter), 1,594 late filings dropped, 400 stock-quarters, and a forward return for all 400.

### Sample period

Signals for the 12 report quarters **2022Q1–2024Q4**. Holdings from 2021Q4 are used to measure the first quarter's change. Forward returns run through May 2025.

### Sample conditions

- **Stocks:** each quarter, the 500 largest U.S. common stocks by 13F-reported institutional dollar holdings. Only information available at that time is used: no "today's S&P 500" list, which would create survivorship bias. REITs and foreign-incorporated firms whose ordinary shares trade in the U.S. (Linde, Accenture) count as common stock. ETFs, ADRs, preferred shares and funds are excluded using OpenFIGI security types. Each issuer enters once, through its larger share class (GOOGL, not also GOOG).
- **No survivors-only filter:** stocks that were acquired or changed CUSIP after the sample (Activision, Pioneer, Lam Research) are kept, through a hand-reviewed CUSIP → ticker map (`data/manual_ticker_map.csv`). Every large candidate we exclude is listed with its reason in `outputs/tables/universe_exclusions.csv`.
- **Managers:** original Form 13F-HR holdings or combination reports filed **on or before the filing deadline**: quarter end + 45 days, moved to the next business day when day 45 falls on a weekend or holiday. Amendments and late filings are excluded, because they were not public at the signal date.
- **Change measures** need the stock to have 13F holders in the previous quarter; a newly listed CUSIP has no "change in crowding" that quarter.
- **Positions:** common shares only. Option positions (`PUTCALL`) and principal-amount rows are excluded.

### Variables

| Absolutely necessary | Nice to have (stretch goals) |
|---|---|
| Manager × stock holdings (13F) | CRSP returns with delistings (removes the survivorship issue below) |
| Filing dates (for timing) | Market capitalization, book-to-market (better controls) |
| CUSIP → ticker map | Hedge-fund-only manager list (the seed's "hedge funds pile in") |
| Daily adjusted prices | Short interest (does crowding + shorting predict crashes?) |
| Market benchmark (SPY) | Longer sample, 2014–2026, including COVID |

### Raw inputs

| Input | Source | How we get it | Where it lives in the repo |
|---|---|---|---|
| Form 13F holdings | [SEC Form 13F data sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets): free, tab-delimited, about 50–150 MB per zip | `src/01_download_13f.py` | `data/raw/sec_13f/` (git-ignored, re-downloadable) |
| CUSIP → ticker, security type | [OpenFIGI API](https://www.openfigi.com/api) | `src/03_universe_and_cusip_map.py`, cached and committed | `data/raw/openfigi_cache.json` |
| Tickers for acquired firms and changed CUSIPs | Hand review of the 13F issuer name (reason and source on every row) | Edited by hand, read by step 3 | `data/manual_ticker_map.csv` |
| Adjusted prices, splits | Yahoo Finance (`yfinance`) | `src/04_download_prices.py`, cached and committed | `data/raw/prices_daily.parquet` |

`data/raw/provenance.csv` logs the URL, pull time and SHA-256 hash of every raw input.

**One detail that shapes the design:** the SEC organizes its 13F files by *filing date*, not by report quarter. For example, the "2023 Q1" zip contains holdings *as of* December 2022. Our code reads every zip, then reassembles holdings by report quarter.

## Method

### Pipeline (one script per step, all run by `run_all.py`)

| Step | File | What it does |
|---|---|---|
| 1 | `src/01_download_13f.py` | Downloads only the SEC zips whose filing window we need |
| 2 | `src/02_parse_13f.py` | Keeps on-time original filings, one per manager-quarter. Builds the manager × stock × quarter holdings panel. Converts the $000s → $ value change (Jan 2023) |
| 3 | `src/03_universe_and_cusip_map.py` | Holder counts per stock. CUSIP → ticker via OpenFIGI. Top-500 universe per quarter |
| 4 | `src/04_download_prices.py` | Adjusted prices and split events for the universe and SPY |
| 5 | `src/05_build_dataset.py` | Crowding measures, formation dates, forward and control returns. Writes the final dataset |
| 6 | `src/06_analysis.py` | Sorts, regressions, cost-adjusted magnitudes, figures, specification log |
| 7 | `src/07_hand_checks.py` | Re-computes one number per step from the raw files with independent code |
| 8 | `src/08_export_site_data.py` | Packages `outputs/` into the single data file the dashboard reads |

### Timing: no look-ahead

```
 quarter end q          deadline (q end + 45 days)     next deadline
      |------------------------|*-----------------------------|*
      holdings measured        formation_date: buy at close   holding_end_date
      (NOT public yet)         (first trading day after)      ret_fwd measured over this window
```

A 13F describes holdings on the last day of the quarter, but the public sees it up to 45 days later. Every return in our tests starts **after** the filing deadline. To show why this matters, we also run the main test with the wrong timing (returns starting at quarter end) and report both in `outputs/tables/lookahead_comparison.csv`.

### Analysis

1. **Quintile sorts.** Each quarter, sort stocks into five groups by each crowding measure. Average the next-quarter return minus SPY in each group. The long–short spread is quintile 5 (most crowded) minus quintile 1. We report its mean, its t-statistic across quarters and the share of quarters it is positive.
2. **Fama–MacBeth regressions.** Each quarter, regress next-quarter excess return on the crowding measure plus controls for past return, volatility and size. All variables are standardized within the quarter, so each coefficient reads as "return per one standard deviation." We average the coefficients across quarters.
3. **Pooled OLS** with quarter fixed effects and standard errors clustered by stock, as a robustness check.
4. **Economic magnitude.** We turn the spread into a strategy and subtract trading costs: quintile turnover × 10 bp per side. Is the gross spread large enough to matter to a risk manager after costs?

**Why this fits the question.**  Quintile sorts allow us to compare returns between the most crowded and least crowded stocks. Fama–MacBeth regressions help us determine whether crowding still explains future returns after accounting for other factors, such as past performance and company size. Both methods are commonly used in asset-pricing research and connect to what we have learned in class.

**Guarding against p-hacking.** `dbreadth` is the pre-registered primary signal. The other three measures are reported in full, not cherry-picked. `06_analysis.py` writes every specification it runs to `outputs/tables/specs_run.csv`, and `specs_tried.md` logs every other change by hand.

## First evidence from v0

The v0 run covers only four quarters (2023, the 100 largest stocks), so these numbers test that the method works. They are not our answer. Source: `outputs/tables/`.

| Crowding quintile (`dbreadth`) | Q1 (least) | Q2 | Q3 | Q4 | Q5 (most) |
|---|---|---|---|---|---|
| Avg next-quarter return minus SPY | −1.6% | −2.6% | −1.0% | −0.6% | +3.5% |

| Test | Estimate | t-stat | p-value |
|---|---|---|---|
| Q5 − Q1, filing-date timing (correct) | **+5.18% per quarter** | 2.11 | 0.13 |
| Q5 − Q1, quarter-end timing (look-ahead) | +6.81% per quarter | 2.39 | 0.10 |
| Fama–MacBeth, per 1 SD of `dbreadth`, with controls | +0.91% per quarter | 2.17 | 0.12 |
| Pooled OLS, quarter fixed effects, clustered by stock | +1.06% per quarter | 1.15 | 0.25 |
| Q5 − Q1 after trading costs (62% leg turnover, 10 bp/side) | +4.93% per quarter | | |

*p-values for the sorts and Fama–MacBeth use the t distribution with 3 degrees of freedom (4 quarters).*

**What this suggests so far.** In 2023, stocks that more managers moved into *outperformed* in three of four quarters. That leans toward the informed-buying story and against our pre-stated hypothesis, but **none of the `dbreadth` tests is significant at the 5% level**. The look-ahead version overstates the spread by about 1.6 points per quarter, which is the bias our timing rule removes. One exploratory result, which we did not pre-register: the *level* of crowding has the opposite sign. Stocks with more holders earned about −2.1% per SD after controlling for size (pooled OLS t = −2.5, p = 0.01; Fama–MacBeth p = 0.09). It is the strongest of the 13 specifications we ran, so we treat it as a lead to test in the full sample, not a finding.

**Why we don't trust it yet.** There are four quarters, and 2023 was dominated by the AI rally: NVDA is in the top crowding quintile, and dropping it cuts the spread from +5.2% to +4.1% per quarter (p = 0.16). The full 2022–2024 run, which includes the 2022 bear market, is the real test.

## Threats and checks

| How an auditor could break the project | What we do |
|---|---|
| **Look-ahead:** using quarter-end dates instead of filing dates | Returns start the first trading day after quarter end + 45 days. Late filings and amendments are dropped. An `assert` checks that formation follows the deadline. We report the wrong-timing result side by side |
| **CUSIP → ticker mapping errors** | OpenFIGI with a preference for the U.S. composite listing of common stock. Every 13F name vs. OpenFIGI name mismatch is written to `cusip_name_mismatches.csv` and reviewed by hand. CUSIPs that collide on one ticker keep the larger holding, and each issuer enters once |
| **Survivorship in the universe:** OpenFIGI only knows today's listings | The universe is built point-in-time from 13F, not from today's index. Acquired firms and changed CUSIPs are kept through a hand-reviewed map; CINS codes are retried with OpenFIGI's CINS lookup. Every large excluded candidate and its reason is in `universe_exclusions.csv` and on the dashboard |
| **Survivorship in returns:** Yahoo drops delisted tickers | The share of stock-quarters missing a return is reported in `return_coverage.csv` and disclosed. CRSP is the fix if we gain access |
| **Weekend deadlines** | When day 45 is a weekend or holiday, the deadline (and so the formation date) moves to the next business day, as the SEC's rules do |
| **New listings look "crowded"** | A stock with no 13F holders last quarter gets no change-in-crowding value, instead of landing in the top quintile by construction |
| **Size of the 13F files** | Zips are git-ignored and re-downloaded. Information tables are read in 1-million-row chunks and filtered immediately. Holdings are stored per quarter as Parquet |
| **13F unit change and filer errors** | $000s → $ conversion by filing date (2023-01-03). The size ranking uses the median implied price across filers, so a few mis-reporting filers can't move it |
| **Stock splits** fake "buying" | Last quarter's shares are multiplied by the Yahoo split factor between the two quarter ends before buyers and sellers are counted |
| **Broken merges / duplicate keys** | Every merge uses `validate=`. Keys are asserted unique at every stage |
| **Numbers that don't trace** | The dashboard reads only `outputs/`. Headline numbers come from `outputs/tables/headline_numbers.json` |
| **Hand checks** | `07_hand_checks.py` re-counts one stock's holders straight from the raw zips, recomputes one return from raw prices, re-derives one formation date, and re-sorts one quarter by hand. Any mismatch stops `run_all.py` |
| **Short sample (12 quarters)** | Every test reports a p-value with the right degrees of freedom (11 in the full sample, 3 in v0). We emphasize magnitudes and hit rates, report every specification, and propose extending to 2014–2026 |
| **One stock drives a quintile** | Leave-one-out and value-weighted spreads in the full sample |

## Dashboard

The dashboard is a single self-contained web page (`index.html`), hosted on GitHub Pages at **https://jdt227.github.io/fin331-final-project/**. It uses no external libraries, so it will keep working for years. It reads only `outputs/site_data.js`, which `src/08_export_site_data.py` builds from `outputs/`, so every number on the page traces to a file there. It has four tabs:

- **Overview:** the question and headline numbers
- **Methodology:** the pipeline and timing rules, plus how many filings each rule removed
- **Results:** quintile bar chart, long–short table, look-ahead comparison, regressions and costs
- **Crowding explorer:** pick any ticker to see its crowding score and holder count over time, or pick a quarter to see the most crowded stocks

![Dashboard, Overview tab](images/dashboard_v0.png)

*Screenshot of the working dashboard (Overview tab) with the real v0 results. The other tabs hold the methodology, the full results and the crowding explorer.*

## Timeline

| Date | Deliverable |
|---|---|
| Sat Nov 14 | **v0:** pipeline on the 2023 sample (`CROWD_QUICK=1`), dashboard skeleton, this proposal, self-audit |
| Sat Nov 21 | **v1:** full 2022–2024 sample, results in the dashboard, response to the AI audit |
| Dec 1 / Dec 3 | Presentation; final repo |

## References

- Brown, G. W., P. Howard, and C. T. Lundblad (2022). Crowded trades and tail risk. *Review of Financial Studies* 35(7), 3231–3271.
- Chen, J., H. Hong, and J. C. Stein (2002). Breadth of ownership and stock returns. *Journal of Financial Economics* 66, 171–205.
- Lakonishok, J., A. Shleifer, and R. W. Vishny (1992). The impact of institutional trading on stock prices. *Journal of Financial Economics* 32, 23–43.
- Sias, R. W. (2004). Institutional herding. *Review of Financial Studies* 17, 165–206.
- U.S. Securities and Exchange Commission. *Form 13F Data Sets* and *Form 13F Data Sets readme* (`form_13f_readme.pdf`).
