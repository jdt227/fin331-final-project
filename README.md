# Crowded Trades: What Happens When the Institutions Pile In?

**Question.** Do stocks that many institutional managers bought last quarter do worse over the next quarter? In other words, is "crowding" a risk?

**Who would pay for the answer.** A risk manager at a hedge fund or asset manager who needs to know whether positions shared with many other funds carry hidden downside.

| | |
|---|---|
| **Dashboard** | `[add Streamlit Cloud link after deploying]` |
| **Dashboard code** | `app.py` in this repo (`streamlit run app.py`) |
| **Proposal** | [`PROPOSAL.md`](PROPOSAL.md) |
| **Checkpoint 1 memo** | [`STATUS.md`](STATUS.md) |
| **Specifications log** | [`specs_tried.md`](specs_tried.md) and `outputs/tables/specs_run.csv` |
| **Audits** | [`audits/`](audits/) |
| **Presentation** | `presentation/` *(added before Dec 1)* |

---

## How to run it

```bash
# 1. Set up (Python 3.10+)
pip install -r requirements.txt

# 2. The SEC blocks downloads that don't identify you
export SEC_USER_AGENT="Your Name your.email@lehigh.edu"      # Windows PowerShell: $env:SEC_USER_AGENT="..."
export OPENFIGI_API_KEY="..."   # optional, free at openfigi.com; makes CUSIP mapping ~10x faster

# 3. Rebuild everything from the raw inputs
python run_all.py                    # full sample: 2022Q1-2024Q4, 500 largest stocks
CROWD_QUICK=1 python run_all.py      # v0 small sample: 2023 only, 100 largest stocks

# 4. Dashboard
streamlit run app.py
```

On Windows PowerShell, set variables first instead: `$env:CROWD_QUICK="1"; python run_all.py`.

`run_all.py` runs the seven scripts in `src/` in order and stops on the first error. Downloads are cached in `data/raw/`, so a second run skips them. Use `python run_all.py --from 5` to re-run only the later steps.

**Storage.** The SEC zip files are roughly 50–150 MB each, about 1–2 GB for the full sample. They are git-ignored, and `src/01_download_13f.py` re-creates them. Everything in `outputs/` is small and committed.

**Testing without internet.** `python tests/make_fake_raw.py /tmp/crowd_test` writes a small fake data set in the exact SEC, OpenFIGI and price formats, with built-in traps: late filers, amendments, duplicate filings, option rows, the 2023 change in value units, an ETF, a stock split and a delisted ticker. The pipeline runs on it end to end:

```bash
CROWD_DATA_DIR=/tmp/crowd_test/data CROWD_OUTPUT_DIR=/tmp/crowd_test/outputs \
CROWD_UNIVERSE_SIZE=40 CROWD_CANDIDATE_POOL=60 python run_all.py
```

## Repository map

```
run_all.py                       one command rebuilds every table and figure
app.py                           Streamlit dashboard (reads only outputs/)
src/
  config.py                      every setting: sample, timing rules, file list
  common.py                      small shared helpers
  01_download_13f.py             SEC Form 13F zips  -> data/raw/sec_13f/
  02_parse_13f.py                on-time original filings -> manager x stock x quarter
  03_universe_and_cusip_map.py   holder counts, CUSIP->ticker (OpenFIGI), top-500 universe
  04_download_prices.py          adjusted prices + splits (Yahoo Finance)
  05_build_dataset.py            crowding measures + forward returns -> outputs/final_dataset.csv
  06_analysis.py                 sorts, Fama-MacBeth, pooled OLS, costs, figures
  07_hand_checks.py              independent re-computation of one number per step
tests/make_fake_raw.py           offline test data in the real formats
data/raw/                        raw inputs (+ provenance.csv: source and pull time of each)
data/interim/                    parsed intermediate files (git-ignored)
outputs/                         final dataset, tables/, figures/ (every number shown comes from here)
images/                          dashboard mockup
audits/                          self-audits and responses to instructor audits
```

## Data and provenance

| Raw input | Source | How we get it | Where it lives |
|---|---|---|---|
| Form 13F holdings | [SEC Form 13F data sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets) (free, quarterly, tab-delimited) | `src/01_download_13f.py` | `data/raw/sec_13f/*.zip` |
| CUSIP → ticker, security type | [OpenFIGI mapping API](https://www.openfigi.com/api) | `src/03_universe_and_cusip_map.py` (cached) | `data/raw/openfigi_cache.json`, `data/raw/cusip_ticker_map.csv` |
| Daily adjusted prices, splits | Yahoo Finance via `yfinance` | `src/04_download_prices.py` | `data/raw/prices_daily.parquet` |

`data/raw/provenance.csv` records the URL, pull time (UTC), file size and SHA-256 hash of every raw input.

## Unit of observation

One row of `outputs/final_dataset.csv` is **one stock × one 13F report quarter**. The key `(ticker, quarter)` is unique, and so is `(cusip, quarter)`. Both are checked with `assert` in `src/05_build_dataset.py`, and every merge uses `validate=`.

## Threats to validity

What we already know could be wrong, and what we do about it:

1. **Look-ahead from quarter-end dates.** 13F holdings are not public until up to 45 days after quarter end. We start every return on the first trading day *after* the deadline, and we drop filings made after the deadline. As a check, `outputs/tables/lookahead_comparison.csv` shows how much the answer changes under the wrong (quarter-end) timing.
2. **Amendments.** 13F-HR/A filings arrive later and can restate holdings. We use original filings only, so the data match what was public at the signal date. This undercounts holdings for managers whose originals were incomplete.
3. **Survivorship in returns (biggest known limitation).** Yahoo Finance drops most delisted tickers. A stock that was in our universe and later got acquired or delisted may have no price data. `outputs/tables/return_coverage.csv` reports how many stock-quarters lose their return. The direction of the bias is unclear: acquisitions usually end with a price jump, while failures end with a crash. CRSP would fix this, and is a stretch goal.
4. **CUSIP → ticker mapping.** OpenFIGI returns a security's *current* ticker. If a ticker has been reused by another company, the mapping can be wrong. We flag every universe stock whose 13F issuer name and OpenFIGI name disagree (`outputs/tables/cusip_name_mismatches.csv`) and review that list by hand.
5. **Universe selection.** The universe is the 500 largest common stocks by 13F-reported dollar holdings at each quarter. It uses only information available then, not today's S&P 500 list. It is a proxy for market cap, not market cap itself.
6. **Reporting errors in 13F values.** Some filers report dollars when they should report thousands, or the reverse. Holder counts don't use values. The size ranking uses each stock's *median* implied price across filers, so a few bad filers can't move it.
7. **Stock splits.** Share counts are not split-adjusted in 13F filings. The buyer and seller measure adjusts last quarter's shares by the Yahoo split factor between the two quarter ends.
8. **Short sample.** The sample has 12 quarters, so time-series t-statistics are noisy. We report magnitudes, hit rates and costs, not just stars, and list every specification we ran.
9. **13F coverage.** 13F filings cover long US equity positions of managers above $100M only. Short positions, derivatives and smaller funds are invisible to us.

## Team

Harrison Babuschak, `[teammate]`, `[teammate]`, `[teammate]`. FIN 331 Data Science for Finance, Lehigh University, Fall 2026.

## References

- Chen, J., H. Hong, and J. Stein (2002). Breadth of ownership and stock returns. *Journal of Financial Economics* 66, 171–205.
- Lakonishok, J., A. Shleifer, and R. Vishny (1992). The impact of institutional trading on stock prices. *Journal of Financial Economics* 32, 23–43.
- Sias, R. (2004). Institutional herding. *Review of Financial Studies* 17, 165–206.
- Brown, G., P. Howard, and C. Lundblad (2022). Crowded trades and tail risk. *Review of Financial Studies* 35(7), 3231–3271.
