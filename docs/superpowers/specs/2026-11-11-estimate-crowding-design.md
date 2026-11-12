# Design: Estimate-Driven Crowding and Earnings Fragility

**Date:** 2026-11-11
**Course:** FIN 331 — Seed 9 (enhanced)

---

## Intent and Why

Test whether large analyst estimate revisions drive institutional crowding, and whether crowded positions entering earnings produce worse stock outcomes. Three amplifiers layer on top of the base crowding effect: estimate momentum (consecutive upward revision streaks), analyst dispersion (disagreement among analysts), and post-earnings drift. The goal is to show a *mechanism* (revisions → crowding → fragility), not just a statistical pattern.

**Who pays:** A risk manager at a multi-manager fund wants to flag "crowded consensus trades" before earnings — positions where analysts keep upgrading and institutions are piling in, but the bar is now too high and dispersion signals uncertainty about whether earnings will clear it.

---

## Goals

1. Show the crowding channel: large estimate revisions predict more new 13F filers the next quarter.
2. Show earnings fragility: high crowding + high revision momentum → worse CAR at earnings [−1,+1].
3. Show dispersion amplifies the effect: high analyst disagreement + crowded = worst outcomes.
4. Show post-earnings drift: crowded stocks that disappoint keep falling for 60 days after earnings.
5. Build a dashboard: a three-factor risk screen (revision streak, crowding, dispersion) with upcoming earnings dates.

## Non-Goals

- Not a live trading system.
- US equities only (no international stocks).
- Not testing the base crowding-predicts-underperformance result in isolation — that's the base seed, not this project.

## Anti-Goals

- Any result that amounts to "crowded stocks underperform" without the estimate revision channel — that's the seed alone and won't score on creativity.
- Any look-ahead bias, even subtle (e.g., using quarter-end 13F data before the filing is public).

---

## Constraints

- All raw data must be free or university-accessible (IBES via WRDS, SEC 13F, yfinance).
- Must reproduce end-to-end from `run_all.py` on a fresh machine.
- EDGAR request delay ≥ 0.12s (per EDGAR terms of service).
- WRDS pulls done once and stored in `inputs/ibes/`; not re-pulled on every run.
- S&P 500 constituent history used for the universe — no survivorship bias from using today's membership.

---

## Unit of Observation

**Stock × fiscal quarter.** One row = a firm in a quarter where we observe:

| Column | Description |
|---|---|
| `ticker` | Stock ticker |
| `fiscal_quarter` | Fiscal quarter end date (e.g., 2023-09-30) |
| `eps_consensus_t` | IBES mean EPS estimate for the **same target fiscal period**, measured as of the quarter end date (snapshot at Q-end) |
| `eps_consensus_tm1` | IBES mean EPS estimate for the **same target fiscal period**, measured as of the prior quarter end (earlier snapshot) |
| `eps_revision` | `(eps_consensus_t − eps_consensus_tm1) / |eps_consensus_tm1|` — how much the consensus for *this* quarter's EPS changed between the two snapshot dates; this is the standard "revision" definition in the literature, not a comparison across two different fiscal periods |
| `revision_streak` | Consecutive quarters of upward revision (0, 1, 2, 3+) |
| `dispersion` | Std dev of analyst estimates / |mean estimate| (coefficient of variation) |
| `n_analysts` | Number of analysts contributing to the consensus |
| `n_filers` | Number of 13F institutions holding the stock at quarter end |
| `chg_filers` | Quarter-over-quarter change in n_filers |
| `crowding_rank` | Percentile rank of n_filers within quarter (normalized for size) |
| `eps_actual` | Actual EPS reported (from IBES or yfinance) |
| `eps_surprise` | `(eps_actual − eps_consensus_t) / |eps_consensus_t|` |
| `earn_date` | Earnings announcement date |
| `car_event` | Market-adjusted CAR[−1,+1] around earnings announcement (stock return minus SPY return over same window, consistent with HW6 machinery) — **builder call: use market-adjusted, not raw or factor-adjusted** |
| `car_drift` | Market-adjusted CAR[+2,+60] after earnings announcement (same benchmark) |

A few real example rows will be shown in `PROPOSAL.md` using 2023 Q3 data.

---

## Sample Period

**2019 Q1 – 2024 Q4** (6 years, 24 quarters). This covers COVID selloff (Q1 2020), meme stock frenzy (early 2021), 2022 rate shock, and the 2023–2024 AI rally — four distinct market regimes to comment on.

---

## Sample Conditions

- S&P 500 constituent as of each historical quarter (no survivorship bias — use constituent history, not today's membership).
- Minimum 5 IBES analysts covering (consensus is meaningful).
- Minimum 10 13F filers holding (crowding signal is not noise).
- Earnings announcement date available in yfinance or IBES.
- Fiscal year end must be identified to separate fiscal-year-end quarters (restated numbers risk) — flag these in a column but do not exclude by default.

---

## Variables

### Absolutely necessary

- `eps_revision`: quarter-over-quarter change in consensus EPS (normalized); winsorize at 1st/99th percentile before use to handle near-zero EPS blow-ups — **builder call: winsorize first, then compute streak**
- `revision_streak`: consecutive quarters with eps_revision > 1% (materiality threshold) — **builder call: 1% minimum to avoid noise from rounding**
- `dispersion`: coefficient of variation of analyst estimates
- `crowding_rank`: percentile rank of n_filers within quarter, computed over **all S&P 500 constituents in that calendar quarter** (not just the filtered analysis sample) — **builder call: use full S&P 500 universe for ranking to avoid censoring the bottom of the distribution**
- `chg_filers`: change in number of 13F filers
- `eps_surprise`: standardized earnings surprise
- `car_event`: market-adjusted CAR[−1,+1] around earnings (stock minus SPY)
- `car_drift`: market-adjusted CAR[+2,+60] after earnings (stock minus SPY)

### Nice to have if possible

- `size`: log market cap (from yfinance `ticker.info`)
- `sector`: GICS sector (from yfinance `ticker.info`)
- `short_interest`: bi-monthly FINRA data (adds short-sellers-vs-crowded-longs angle)
- `n_analysts`: number of contributing analysts (quality of consensus)

---

## Raw Inputs

| Input | Source | How to get it | Where it lives |
|---|---|---|---|
| IBES consensus EPS (mean, std, n, actual, announcement date) | WRDS — `ibes.statsum_epsus` | WRDS web query or `wrds` Python package; pull once, save CSV | `inputs/ibes/ibes_consensus.csv` |
| 13F index (which filers filed each quarter) | SEC EDGAR quarterly index | `code/01_get_13f_filings.py` (already built) | `inputs/13f_index/` |
| 13F holdings (what each filer held) | SEC EDGAR infotable XML | `code/02_get_holdings.py` (already built) | `inputs/13f_holdings/` |
| CUSIP → ticker mapping | OpenFIGI API | `code/02_get_holdings.py` (already built) | inside holdings files |
| Daily adjusted close prices | yfinance | `code/04_get_returns.py` (already built) | `inputs/returns/` |
| S&P 500 constituent history | Wikipedia "List of S&P 500 companies" (history tab) or a stored CSV | Scrape or manual download once | `inputs/sp500_history.csv` |

---

## Method (Pipeline Steps)

The existing pipeline has files `01` through `06`. The new structure:

1. **`code/01_get_ibes.py`** — Pull IBES `statsum_epsus` for US stocks, 2019–2024. Keep columns: ticker (via CUSIP link), fiscal quarter end date, mean estimate, std estimate, n analysts, actual EPS, announcement date. Store as `inputs/ibes/ibes_consensus.csv`.

2. **`code/02_get_13f_filings.py`** — Existing: pull 13F index from EDGAR quarterly index files.

3. **`code/03_get_holdings.py`** — Existing: download individual 13F infotable XMLs and extract holdings.

4. **`code/04_build_crowding.py`** — Existing: aggregate holdings to stock × quarter crowding scores (n_filers, chg_filers, frac_filers).

5. **`code/05_get_returns.py`** — Existing: download daily adjusted close prices from yfinance.

6. **`code/06_build_dataset.py`** — Merge IBES + crowding + returns on (ticker, fiscal_quarter). Compute: eps_revision, revision_streak, dispersion, crowding_rank, eps_surprise, car_event, car_drift. Assert unique keys. Run `validate=` on all merges. Save `inputs/final_dataset.parquet`.

7. **`code/07_analysis.py`** — Sorts and regressions:
   - **Channel test:** sort by eps_revision quintile → next-quarter chg_filers (does the crowding come after the revision?)
   - **Fragility test:** sort by crowding_rank quintile → car_event (do crowded stocks disappoint at earnings?)
   - **Interaction table:** 2×2 of high/low crowding × high/low dispersion → mean car_event
   - **Streak effect:** revision_streak (0,1,2,3+) × crowding_rank quintile → car_event heatmap
   - **Post-earnings drift:** car_drift by crowded vs. not crowded, with a CAR time-series plot
   - **Regression:** `car_event ~ eps_revision + revision_streak + dispersion + crowding_rank + size + sector_FE + quarter_FE`, HC3 robust SEs

8. **`app.py`** (dashboard) — Three tabs (see Dashboard section below).

---

## Threats and Checks

| Threat | Mitigation |
|---|---|
| **Look-ahead from 13F filing date** | Use a **uniform one-quarter lag**: crowding from quarter Q (13F public ~45 days after Q ends) predicts CAR at earnings in quarter Q+1. This is conservative — some late reporters are unaffected — but it is simple, reproducible, and fully safe. Document this rule explicitly in README. **Builder call: uniform lag, not per-filer actual filing dates.** |
| **Fiscal vs. calendar quarter alignment** | IBES fiscal quarters may not align with 13F calendar quarters for non-December FYE firms. Rule: for each IBES fiscal quarter, join to the most recent 13F calendar quarter end that falls **on or before** the fiscal quarter end date. This avoids look-ahead (never joins to a future 13F quarter). For December FYE firms it is a perfect match; for others the 13F may be 1–2 months stale. Document non-December FYE firms as an approximation; flag `fiscal_qtr_match` column (exact vs. approximate) for sensitivity analysis. **Builder call: use this rule; do not restrict to December FYE only.** |
| **Survivorship bias** | Use S&P 500 membership as of each historical quarter, not today's. |
| **CUSIP → ticker mismatches** | Hand-check a random sample of 50 mappings; report hit rate in README. |
| **Size confound** | Large stocks always have more 13F holders. Use `crowding_rank` (percentile within quarter) in regression, not raw n_filers. |
| **Multiple testing / p-hacking** | Log all specifications tried in `specs_tried.md`. |
| **Earnings timing (pre vs. post-market)** | Some firms announce before open (day 0 = that day), others after close (day 0 = next trading day). Use yfinance timestamps to flag; handle in CAR computation. |
| **Estimate revision scaling** | Revisions for near-zero EPS forecasts blow up when normalized. Winsorize eps_revision at 1st/99th percentile; document and check results with and without. |
| **IBES selection bias** | IBES covers larger, well-followed firms — document as a sample condition, not a threat to internal validity. Note external validity limit in README. |

**Hand-checks (at least one per pipeline step):**
- Step 6: pick one stock (e.g., AAPL, 2023 Q3) and recompute eps_revision, crowding_rank, and car_event by hand from raw files. Must match.
- Step 7: recompute one quintile's mean car_event in a separate notebook cell.

---

## Dashboard

Three tabs in `app.py` (Streamlit):

**Tab 1 — Risk Screen**
Scatter plot: x-axis = revision_streak (0–3+), y-axis = chg_filers (percentile), dot color = dispersion level (low/medium/high), dot size = market cap. Quadrant lines mark the "danger zone" (top-right: long streak + lots of new holders + high dispersion). Hover shows ticker, upcoming earnings date, current crowding percentile. Filter by sector.

**Tab 2 — Earnings Outcomes**
Bar chart of mean car_event by (revision_streak × crowding_rank) bucket. Slider for holding period (+1 to +60 days) to show post-earnings drift evolving. Table with count, mean, and 95% CI for each bucket.

**Tab 3 — Stock Explorer**
Type any ticker → see: revision history (line chart), crowding history (bar chart), past earnings outcomes (scatter of surprise vs. car_event), and the stock's historical "danger zone" classification.

---

## Left to the Builder

- Exact WRDS Python query for `ibes.statsum_epsus` (fiscal period codes, US stock filter, date range). The builder should check whether `fpedats` or `anndats` is the right date field for aligning with 13F quarter ends.
- S&P 500 constituent history: builder should decide between Wikipedia scrape and a stored CSV committed to the repo (stored CSV is more reproducible).
- Timing flag for pre/post-market earnings announcements: builder decides whether to use yfinance's `ticker.calendar` or IBES `anndats_act` field.
- Whether to renumber existing pipeline files (01–06) or add the IBES step as a new 01 and shift others.
- Storage plan for 13F holdings files — the seed warns these are large. Builder should document total download size and confirm disk is sufficient before running.
