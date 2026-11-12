# Checkpoint 2 Status — Estimate-Driven Crowding

**Date:** 2026-11-11  
**Team:** Solo  
**Course:** FIN 331 — Financial Data Analytics  

---

## 1. What we picked and why

We are testing whether large analyst EPS estimate revisions drive institutional
crowding, and whether crowded positions entering earnings produce worse outcomes
(lower CAR and slower post-earnings recovery). We chose this angle because it
links two well-studied phenomena — analyst herding and crowded trades — through
a single causal channel that is testable with available data.

The three enhancements over the base seed:
- **Analyst dispersion** (coefficient of variation of estimates) as a risk
  signal separate from the consensus direction
- **Revision streak** (consecutive quarters of positive revisions) to capture
  momentum in analyst sentiment
- **Post-earnings drift** (CAR[+2,+60]) to test whether crowded stocks
  revert slowly or quickly after the event

---

## 2. Proof-of-concept results

The pipeline is fully wired end-to-end on a 20-ticker, 2022–2023 synthetic
dataset. The dashboard (4 tabs) is running and displays all five analysis
figures. Key numbers from the checkpoint run:

| Metric | Value |
|--------|-------|
| Stock-quarter observations | 180 |
| Unique tickers | 20 |
| CAR data coverage | 100% |
| Tests passing | 37 / 37 |

The fragility sort shows the expected pattern on synthetic data (Q5 most-
crowded has lower CAR[-1,+1] than Q1). The 2×2 table shows that high-
crowding × high-revision is the worst quadrant (mean CAR ~ −1.2%), consistent
with the hypothesis. These results are illustrative — real IBES and 13F data
are needed for inference.

**Data caveat:** IBES consensus is currently a synthetic placeholder (20
tickers × 9 quarters). Real data requires a Python 3.11 environment with the
`wrds` package. The 13F pipeline code is complete but has not been run against
EDGAR yet due to download time constraints.

---

## 3. Questions for professor

1. **WRDS access from Python 3.14**: The `wrds` package fails to build on
   Python 3.14 (pandas compilation error). We plan to use a `conda` environment
   with Python 3.11 to pull the real IBES data. Is that an acceptable workflow,
   or should we target a different data source (e.g., Compustat via WRDS
   instead of IBES)?

2. **Look-ahead rule**: We use a uniform one-quarter lag (crowding rank from
   calendar Q → CAR at earnings in Q+1). An alternative is to use the actual
   13F filing date per filer (variable lag). The variable-lag approach is more
   precise but harder to validate. Which do you prefer?

3. **CAR benchmark**: We are using SPY as the market benchmark for all
   market-adjusted CARs. For sector-heavy stocks (e.g., energy in Q4 2022)
   a sector ETF benchmark might be more appropriate. Should we add a sector-
   adjusted CAR as a robustness check?
