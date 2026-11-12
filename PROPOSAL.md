# Project Proposal — Estimate-Driven Crowding

**Course:** FIN 331 — Financial Data Analytics  
**Date:** 2026-11-11  
**Seed idea:** #9 — Crowded Trades  

---

## Research Question

Do large analyst EPS estimate revisions herd institutions into the same
stocks, and do crowded positions entering earnings produce worse outcomes?

---

## Motivation

Crowded trades — positions held by many hedge funds simultaneously — are
a well-known source of fragility. When a crowded stock misses earnings,
the rush to exit amplifies losses. The standard framing treats crowding as
an independent risk factor. We ask: does analyst consensus *cause* the
crowding in the first place? If institutions react to the same EPS upgrades
by buying the same stocks, then revision momentum is a leading indicator of
crowding, and the worst outcomes should occur when both signals are elevated
simultaneously.

---

## Data

| Dataset | Source | Variables |
|---------|--------|-----------|
| IBES statsum_epsus | WRDS | eps_consensus, std_dev, n_analysts, actual EPS, announcement date |
| SEC Form 13F | EDGAR API | n_filers per stock per quarter |
| Daily returns | yfinance (adjusted close) | Stock returns + SPY benchmark |
| S&P 500 constituents | Wikipedia | Ticker filter |

**Sample:** S&P 500 constituents, 2022–2023 (Checkpoint 2 uses 20 synthetic
tickers; full run targets full S&P 500 history from 2010).

---

## Variables

| Variable | Definition |
|----------|------------|
| `eps_revision` | (consensus_t − consensus_tm1) / \|consensus_tm1\| — winsorized at 1/99th pct |
| `revision_streak` | Consecutive quarters with eps_revision > 1% |
| `dispersion` | analyst std dev / \|eps_consensus\| (coefficient of variation) |
| `crowding_rank` | Percentile of n_filers within S&P 500 that calendar quarter |
| `car_event` | Market-adjusted CAR[-1,+1] around earnings announcement |
| `car_drift` | Market-adjusted CAR[+2,+60] after earnings announcement |
| `eps_surprise` | (actual − consensus) / \|consensus\| |

**Look-ahead rule:** Crowding rank from calendar quarter Q predicts CAR at
earnings in Q+1. 13F filings are public ≈45 days after Q; Q+1 earnings follow.

---

## Analyses

1. **Channel test** — OLS: crowding_rank ~ eps_revision + revision_streak + dispersion  
   Tests whether revisions predict crowding after controlling for uncertainty.

2. **Fragility sort** — Sort stocks into quintiles by crowding_rank; compare
   mean car_event and car_drift across quintiles.

3. **2×2 table** — High/Low crowding × High/Low eps_revision → mean car_event.
   Identifies the worst quadrant (high crowding, high revision).

4. **Interaction regression** — car_event ~ crowding_rank × eps_surprise +
   revision_streak + dispersion + quarter FE.  
   Tests whether crowding amplifies the market reaction to earnings surprises.

---

## Dashboard

A 4-tab Streamlit app:
- **Introduction** — hypothesis, hook stats, data caveat
- **Methodology** — data flow, variable definitions, look-ahead rule
- **Results** — five figures + regression table
- **Explore** — per-ticker time series of crowding, revision, and CAR

---

## Limitations

- **Synthetic data for Checkpoint 2** — IBES and 13F data are placeholders.
  Statistical results are illustrative; inference requires real data.
- **WRDS access on Python 3.14** — requires a Python 3.11 `conda` environment.
- **S&P 500 filter** — using current constituents (survivorship bias); will
  add historical constituent history for the final submission.
- **Single benchmark** — SPY; sector-adjusted robustness check planned.

---

## Timeline

| Milestone | Date |
|-----------|------|
| Checkpoint 2 (this document) | 2026-11-14 |
| Real IBES data loaded | 2026-11-21 |
| 13F pipeline run on full history | 2026-11-21 |
| Final analysis + write-up | 2026-12-01 |
