# Specs Tried — Design Decisions and Alternatives

This log records every specification decision we tried, what worked, what
didn't, and what we chose. It serves as the audit trail required by the
FIN 331 project rubric.

---

## 1. Crowding metric

| Spec | Outcome |
|------|---------|
| `frac_filers` = n_filers / total_filers (normalized) | Tried first; correlated 0.97 with n_filers within quarter — adds no information when percentile rank is used |
| `n_filers` raw count | Used as the input to percentile ranking |
| **`crowding_rank` = percentile of n_filers within S&P 500 that quarter** | **Chosen** — cross-sectionally comparable, bounded [0,1] |

---

## 2. EPS revision definition

| Spec | Outcome |
|------|---------|
| (consensus_t − consensus_t−4) / \|consensus_t−4\| — same quarter, one year ago | Captures drift well but loses the most recent quarterly update signal |
| (actual_t − consensus_t) / \|consensus_t\| — surprise, not revision | Measures surprise, not forward-looking revision momentum |
| **Same fiscal period, two snapshot dates: (consensus_t − consensus_tm1) / \|consensus_tm1\|** | **Chosen** — isolates the marginal update that institutions would react to |

---

## 3. Winsorization

| Spec | Outcome |
|------|---------|
| No winsorization | Extreme revisions (e.g., 500% when prior consensus near zero) dominate the streak calculation |
| Winsorize at 5/95 | Too aggressive — clips genuine large upgrades |
| **Winsorize at 1/99** | **Chosen** — removes pathological outliers while preserving economically meaningful revisions |

---

## 4. Look-ahead rule for 13F crowding

| Spec | Outcome |
|------|---------|
| Zero-lag: use Q crowding → Q earnings | Look-ahead bias — 13F filings not public until ≈45 days after Q end |
| Variable-lag: use actual filing date per filer | More precise but difficult to validate; requires per-filer filing timestamps |
| **Uniform one-quarter lag: Q crowding → Q+1 earnings** | **Chosen** — conservative, easy to audit, standard in the literature |

---

## 5. CAR benchmark

| Spec | Outcome |
|------|---------|
| Raw stock return (no benchmark) | Confounded by market moves during earnings season |
| Sector ETF benchmark | More precise for sector-heavy stocks but harder to implement cleanly |
| **Market-adjusted: stock daily return minus SPY daily return** | **Chosen** — simple, well-understood, removes systematic market risk |

---

## 6. CAR event window

| Spec | Outcome |
|------|---------|
| [0, +1] — post-announcement only | Misses drift from leaked news or after-hours trading on day −1 |
| [−2, +2] — wider window | Picks up pre-announcement leakage but adds noise |
| **car_event = [−1, +1], car_drift = [+2, +60]** | **Chosen** — standard event-study convention; drift window captures PEAD |

---

## 7. Fiscal → calendar quarter alignment

| Spec | Outcome |
|------|---------|
| Use fpedats as-is (may fall mid-month) | Mismatch with 13F quarter ends (always Mar/Jun/Sep/Dec) |
| Round to nearest calendar quarter end | Can introduce future quarter data for January FYE firms |
| **Most recent calendar quarter end on or before fpedats** | **Chosen** — conservative (never forward-looking), documented in `fiscal_qtr_match` column |

---

## 8. Analyst dispersion variable

| Spec | Outcome |
|------|---------|
| Raw std dev of analyst estimates | Not comparable across stocks with different EPS levels |
| Interquartile range of estimates | More robust but less standard |
| **Coefficient of variation = std_dev / \|eps_consensus\|** | **Chosen** — scale-free, interpretable as relative disagreement |

---

## 9. Sample filter

| Spec | Outcome |
|------|---------|
| All 13F filers regardless of S&P 500 membership | Includes micro-caps where crowding dynamics differ |
| Russell 1000 | Better coverage but harder to get historical constituent history |
| **S&P 500 current constituents (approximate)** | **Chosen for checkpoint** — will add historical constituent history for final submission |
| Minimum 5 IBES analysts | Applied — removes thinly covered stocks where consensus is unreliable |

---

## 10. WRDS / Python version

| Spec | Outcome |
|------|---------|
| `wrds` package on Python 3.14 (Anaconda) | Fails: pandas build error during wrds install |
| **Python 3.11 conda env (`conda create -n wrds311 python=3.11 && pip install wrds`)** | **Planned for real data** — checkpoint uses synthetic placeholder |
